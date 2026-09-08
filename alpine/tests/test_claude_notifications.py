"""Claude Code notification integration tests with no model or desktop calls."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/mbp-intel-claude-notify'
INSTALLER = REPO / 'alpine/bin/install-claude-notifications'


class ClaudeNotifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-claude-notify-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls = self.root / 'notify-calls.jsonl'
        notifier = self.bin / 'notify-send'
        notifier.write_text(
            f'#!{sys.executable}\n'
            'import json, os, sys\n'
            'with open(os.environ["NOTIFY_CALLS"], "a") as stream:\n'
            '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n')
        notifier.chmod(0o755)
        self.env = {
            **os.environ,
            'PATH': str(self.bin),
            'NOTIFY_CALLS': str(self.calls),
        }

    def run_helper(self, payload):
        return subprocess.run(
            [sys.executable, str(HELPER)], input=json.dumps(payload), text=True,
            capture_output=True, env=self.env, timeout=5)

    def notifications(self):
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

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
            '--app-name=Claude', '--urgency=critical',
            'Claude • Needs attention']])

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
        expected = [[
            '--app-name=Claude', '--urgency=critical',
            'Claude • Needs attention']] * len(kinds)
        self.assertEqual(self.notifications(), expected)

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
            '--app-name=Claude', '--urgency=normal', 'Claude • Done']])

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


class ClaudeNotificationInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-claude-install-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.claude = self.home / '.claude'
        self.claude.mkdir(parents=True)
        self.helper = self.home / '.local/bin/mbp-intel-claude-notify'
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
