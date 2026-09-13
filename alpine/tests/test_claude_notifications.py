"""Claude Code notification integration tests with no model or desktop calls."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-claude-notify'
INSTALLER = REPO / 'alpine/bin/install-claude-notifications'

CLOSE_CALL = ['call', '--session', '--dest', 'org.freedesktop.Notifications',
             '--object-path', '/org/freedesktop/Notifications', '--method',
             'org.freedesktop.Notifications.CloseNotification']


class ClaudeNotifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-claude-notify-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls = self.root / 'notify-calls.jsonl'
        notifier = self.bin / 'notify-send'
        notifier.write_text(
            f'#!{sys.executable}\n'
            'import json, os, sys\n'
            'with open(os.environ["NOTIFY_CALLS"], "a") as stream:\n'
            '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n'
            'if "--print-id" in sys.argv[1:]:\n'
            '    counter = os.environ["NOTIFY_ID_COUNTER"]\n'
            '    value = int(open(counter).read()) + 1 if os.path.exists(counter) else 1\n'
            '    open(counter, "w").write(str(value))\n'
            '    print(value)\n')
        notifier.chmod(0o755)
        self.gdbus_log = self.root / 'gdbus-calls.jsonl'
        fake_gdbus = self.bin / 'gdbus'
        fake_gdbus.write_text(
            f'#!{sys.executable}\n'
            'import json, os, sys\n'
            'with open(os.environ["GDBUS_CALLS"], "a") as stream:\n'
            '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n')
        fake_gdbus.chmod(0o755)
        self.env = {
            **os.environ,
            'PATH': str(self.bin),
            'NOTIFY_CALLS': str(self.calls),
            'NOTIFY_ID_COUNTER': str(self.root / 'notify-id-counter'),
            'GDBUS_CALLS': str(self.gdbus_log),
            'XDG_RUNTIME_DIR': str(self.runtime),
            'TMUX_PANE': '%9',
        }

    def run_helper(self, payload):
        return subprocess.run(
            [sys.executable, str(HELPER)], input=json.dumps(payload), text=True,
            capture_output=True, env=self.env, timeout=5)

    def notifications(self):
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def gdbus_calls(self):
        if not self.gdbus_log.exists():
            return []
        return [json.loads(line) for line in self.gdbus_log.read_text().splitlines()]

    def records(self):
        root = self.runtime / 'oldbook/claude-events'
        return list(root.glob('*.json')) if root.exists() else []

    def test_permission_request_notifies_without_answering_it(self):
        payload = {
            'hook_event_name': 'PermissionRequest',
            'session_id': 'private-session',
            'cwd': '/private/project',
            'tool_name': 'Bash',
            'tool_input': {'command': 'private command'},
        }
        result = self.run_helper(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '', 'empty stdout leaves the decision to Claude')
        self.assertEqual(self.notifications(), [[
            '--app-name=Claude', '--urgency=critical', '--print-id',
            'Claude • Waiting on you']])
        # The printed id and a private routing record exist so this exact
        # notification can be auto-dismissed and clicked to the right window
        # later, but none of that private routing data is on the command line
        # sent to notify-send above -- the visible banner stays content-free.
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name,
                         hashlib.sha256(b'private-session').hexdigest() + '.json')
        record = json.loads(records[0].read_text())
        self.assertEqual(set(record), {
            'version', 'event', 'observed_at', 'valid_until', 'tmux_pane', 'cwd', 'tty', 'id'})
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['event'], 'permission-requested')
        self.assertEqual(record['tmux_pane'], '%9')
        self.assertEqual(record['cwd'], '/private/project')
        self.assertEqual(record['id'], 1)
        self.assertLessEqual(record['observed_at'], int(time.time()))
        self.assertEqual(record['valid_until'] - record['observed_at'], 300)
        self.assertEqual(stat.S_IMODE(records[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(records[0].parent.stat().st_mode), 0o700)

    def test_supported_input_notifications_are_content_free(self):
        kinds = [
            'permission_prompt',
            'idle_prompt',
            'elicitation_dialog',
            'elicitation_url_dialog',
            'agent_needs_input',
            'quota_auto_resume_stale',
            'quota_auto_resume_disabled',
        ]
        for kind in kinds:
            with self.subTest(kind=kind):
                result = self.run_helper({
                    'hook_event_name': 'Notification',
                    'notification_type': kind,
                    'message': 'private notification contents',
                    'title': 'private title',
                })
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
        # A nudge is not a catastrophe. Red is reserved for the permission
        # request, which is Claude stopped and waiting; sending everything
        # critical is how a desktop teaches you to ignore critical.
        expected = [[
            '--app-name=Claude', '--urgency=normal', '--print-id',
            'Claude • Needs attention']] * len(kinds)
        self.assertEqual(self.notifications(), expected)
        # None of these payloads carried a session_id, so there is nothing to
        # route a later click or auto-dismiss to; no record is written.
        self.assertEqual(self.records(), [])

    def test_attention_notification_with_a_session_writes_a_routing_record(self):
        result = self.run_helper({
            'hook_event_name': 'Notification',
            'notification_type': 'idle_prompt',
            'session_id': 'attention-session',
            'cwd': '/home/jack/other-project',
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.records()
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text())
        self.assertEqual(record['event'], 'attention')
        self.assertEqual(record['id'], 1)
        self.assertEqual(record['cwd'], '/home/jack/other-project')

    def test_a_second_attention_event_for_the_same_session_closes_the_first(self):
        """The documented possible duplicate must not leave two live popups."""
        self.run_helper({
            'hook_event_name': 'PermissionRequest',
            'session_id': 'duplicate-session',
        })
        self.run_helper({
            'hook_event_name': 'Notification',
            'notification_type': 'permission_prompt',
            'session_id': 'duplicate-session',
        })
        records = self.records()
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text())
        self.assertEqual(record['id'], 2)
        self.assertEqual(self.gdbus_calls(), [[*CLOSE_CALL, '1']])

    def test_stop_closes_and_clears_the_routing_record_for_that_session(self):
        self.run_helper({
            'hook_event_name': 'PermissionRequest',
            'session_id': 'resolved-by-stop',
            'cwd': '/home/jack/project',
        })
        self.assertEqual(len(self.records()), 1)
        result = self.run_helper({
            'hook_event_name': 'Stop',
            'session_id': 'resolved-by-stop',
            'background_tasks': [],
            'session_crons': [],
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.records(), [])
        self.assertEqual(self.gdbus_calls(), [[*CLOSE_CALL, '1']])
        # Stop's own low-urgency completion notice still fires alongside the close.
        self.assertEqual(self.notifications()[-1], [
            '--app-name=Claude', '--urgency=low', 'Claude • Done'])

    def test_stop_with_background_work_still_clears_the_routing_record(self):
        self.run_helper({
            'hook_event_name': 'PermissionRequest',
            'session_id': 'still-working',
        })
        result = self.run_helper({
            'hook_event_name': 'Stop',
            'session_id': 'still-working',
            'background_tasks': [{'id': 'private-task'}],
            'session_crons': [],
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.records(), [])
        self.assertEqual(self.gdbus_calls(), [[*CLOSE_CALL, '1']])
        # No 'Done' notice this time -- background work is still active.
        self.assertEqual(len(self.notifications()), 1)

    def test_user_prompt_submit_closes_and_clears_the_routing_record(self):
        self.run_helper({
            'hook_event_name': 'Notification',
            'notification_type': 'agent_needs_input',
            'session_id': 'resolved-by-prompt',
        })
        self.assertEqual(len(self.records()), 1)
        result = self.run_helper({
            'hook_event_name': 'UserPromptSubmit',
            'session_id': 'resolved-by-prompt',
            'prompt': 'private reply',
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.records(), [])
        self.assertEqual(self.gdbus_calls(), [[*CLOSE_CALL, '1']])
        self.assertEqual(len(self.notifications()), 1,
                         'clearing routing metadata must not create a notification')

    def test_clearing_an_untracked_session_does_nothing(self):
        for event in ('Stop', 'UserPromptSubmit'):
            with self.subTest(event=event):
                result = self.run_helper({
                    'hook_event_name': event,
                    'session_id': 'never-tracked',
                    'background_tasks': [], 'session_crons': [],
                })
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.records(), [])
        self.assertEqual(self.gdbus_calls(), [])

    def test_expired_record_is_removed_on_the_next_event(self):
        oldbook = self.runtime / 'oldbook'
        oldbook.mkdir(mode=0o700)
        events = oldbook / 'claude-events'
        events.mkdir(mode=0o700)
        expired = events / ('a' * 64 + '.json')
        expired.write_text(json.dumps({'valid_until': int(time.time()) - 1}))
        expired.chmod(0o600)
        result = self.run_helper({
            'hook_event_name': 'PermissionRequest', 'session_id': 'current',
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(expired.exists())
        self.assertEqual(len(self.records()), 1)

    def test_stop_notifies_only_when_no_background_work_is_reported(self):
        completed = self.run_helper({
            'hook_event_name': 'Stop',
            'last_assistant_message': 'private response',
            'background_tasks': [],
            'session_crons': [],
        })
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, '')
        self.assertEqual(self.notifications(), [[
            '--app-name=Claude', '--urgency=low', 'Claude • Done']])

        for field in ('background_tasks', 'session_crons'):
            with self.subTest(field=field):
                payload = {
                    'hook_event_name': 'Stop',
                    'background_tasks': [],
                    'session_crons': [],
                }
                payload[field] = [{'id': 'private-task'}]
                result = self.run_helper(payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
        unavailable = self.run_helper({'hook_event_name': 'Stop'})
        self.assertEqual(unavailable.returncode, 0, unavailable.stderr)
        self.assertEqual(unavailable.stdout, '')
        self.assertEqual(len(self.notifications()), 1)

    def test_non_attention_notification_types_are_ignored(self):
        kinds = [
            'agent_completed',
            'auth_success',
            'elicitation_complete',
            'elicitation_response',
            'quota_auto_resume_fired',
        ]
        for kind in kinds:
            result = self.run_helper({
                'hook_event_name': 'Notification',
                'notification_type': kind,
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
        self.assertEqual(self.notifications(), [])

    def test_unknown_and_malformed_input_is_ignored(self):
        cases = [
            '{}',
            '[]',
            'not-json',
            '',
        ]
        for content in cases:
            with self.subTest(content=content):
                result = subprocess.run(
                    [sys.executable, str(HELPER)], input=content, text=True,
                    capture_output=True, env=self.env, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
        self.assertEqual(self.notifications(), [])
        self.assertEqual(self.records(), [])
        self.assertEqual(self.gdbus_calls(), [])


class ClaudeNotificationInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-claude-install-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.claude = self.home / '.claude'
        self.claude.mkdir(parents=True)
        self.helper = self.home / '.local/bin/oldbook-claude-notify'
        self.helper.parent.mkdir(parents=True)
        source_helper = Path(self.temp.name) / 'source-helper'
        source_helper.write_text('#!/bin/sh\n')
        source_helper.chmod(0o755)
        self.helper.symlink_to(source_helper)

    def install(self):
        return subprocess.run(
            [sys.executable, str(INSTALLER), '--target', str(self.home),
             '--helper', str(self.helper)],
            text=True, capture_output=True, timeout=5)

    def test_install_preserves_settings_and_existing_hooks(self):
        existing = {
            'theme': 'gruvbox',
            'permissions': {'defaultMode': 'default'},
            'hooks': {
                'PostToolUse': [{
                    'matcher': 'Edit',
                    'hooks': [{'type': 'command', 'command': '/bin/existing'}],
                }],
            },
        }
        original = json.dumps(existing, indent=4) + '\n'
        settings = self.claude / 'settings.json'
        settings.write_text(original)
        settings.chmod(0o640)

        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = json.loads(settings.read_text())
        self.assertEqual(installed['theme'], existing['theme'])
        self.assertEqual(installed['permissions'], existing['permissions'])
        self.assertEqual(installed['hooks']['PostToolUse'],
                         existing['hooks']['PostToolUse'])
        handler = {
            'type': 'command',
            'command': str(self.helper),
            'timeout': 3,
        }
        self.assertEqual(installed['hooks']['PermissionRequest'], [
            {'hooks': [handler]}])
        self.assertEqual(installed['hooks']['Notification'], [{
            'matcher': ('permission_prompt|idle_prompt|elicitation_dialog|'
                        'elicitation_url_dialog|agent_needs_input|'
                        'quota_auto_resume_stale|'
                        'quota_auto_resume_disabled'),
            'hooks': [handler],
        }])
        self.assertEqual(installed['hooks']['Stop'], [{'hooks': [handler]}])
        self.assertEqual(installed['hooks']['UserPromptSubmit'], [{'hooks': [handler]}])
        self.assertEqual(stat.S_IMODE(settings.stat().st_mode), 0o640)

        backup = Path(result.stdout.strip())
        self.assertEqual(backup.joinpath('settings.json').read_text(), original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(
            backup.joinpath('settings.json').stat().st_mode), 0o600)

    def test_install_is_idempotent_for_its_exact_handlers(self):
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stderr)
        first_settings = self.claude.joinpath('settings.json').read_bytes()
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.claude.joinpath('settings.json').read_bytes(),
                         first_settings)
        hooks = json.loads(first_settings)['hooks']
        self.assertEqual(len(hooks['PermissionRequest']), 1)
        self.assertEqual(len(hooks['Notification']), 1)
        self.assertEqual(len(hooks['Stop']), 1)
        self.assertEqual(len(hooks['UserPromptSubmit']), 1)

    def test_broken_settings_symlink_is_never_replaced(self):
        settings = self.claude / 'settings.json'
        settings.symlink_to(self.home / 'missing-settings')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('non-regular file', result.stderr)
        self.assertTrue(settings.is_symlink())

    def test_rollback_restores_exact_settings(self):
        original = b'{"theme":"keep-exactly"}\n'
        settings = self.claude / 'settings.json'
        settings.write_bytes(original)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        rollback = subprocess.run(
            [sys.executable, str(INSTALLER), '--target', str(self.home),
             '--rollback', str(backup)], text=True, capture_output=True,
            timeout=5)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(settings.read_bytes(), original)

    def test_rollback_removes_settings_created_by_install(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        rollback = subprocess.run(
            [sys.executable, str(INSTALLER), '--target', str(self.home),
             '--rollback', str(backup)], text=True, capture_output=True,
            timeout=5)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertFalse(self.claude.joinpath('settings.json').exists())

    def test_rollback_refuses_after_a_later_settings_change(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        settings = self.claude / 'settings.json'
        settings.write_text('{"user":"change"}\n')
        rollback = subprocess.run(
            [sys.executable, str(INSTALLER), '--target', str(self.home),
             '--rollback', str(backup)], text=True, capture_output=True,
            timeout=5)
        self.assertNotEqual(rollback.returncode, 0)
        self.assertIn('changed since installation', rollback.stderr)
        self.assertEqual(settings.read_text(), '{"user":"change"}\n')


if __name__ == '__main__':
    unittest.main()
