"""Codex notification integration tests with no model or desktop calls."""
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
import runpy


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-codex-notify'
INSTALLER = REPO / 'alpine/bin/install-codex-notifications'


class CodexNotifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-codex-notify-')
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
            '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n')
        notifier.chmod(0o755)
        self.env = {
            **os.environ,
            'PATH': str(self.bin),
            'NOTIFY_CALLS': str(self.calls),
            'XDG_RUNTIME_DIR': str(self.runtime),
            'TMUX_PANE': '%17',
        }

    def run_helper(self, mode, payload):
        command = [sys.executable, str(HELPER), mode]
        if mode == '--notify':
            command.append(json.dumps(payload))
            stdin = None
        else:
            stdin = json.dumps(payload)
        return subprocess.run(command, input=stdin, text=True, capture_output=True,
                              env=self.env, timeout=5)

    def notifications(self):
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def records(self):
        root = self.runtime / 'oldbook/codex-events'
        return list(root.glob('*.json')) if root.exists() else []

    def test_controlling_tty_number_maps_without_inherited_standard_descriptors(self):
        module = runpy.run_path(str(HELPER))
        self.assertEqual(module['tty_path'](34819), '/dev/pts/3')
        self.assertEqual(module['tty_path'](1025), '/dev/tty1')
        self.assertIsNone(module['tty_path'](0))

    def test_completion_is_content_free_and_records_transient_routing_metadata(self):
        payload = {
            'type': 'agent-turn-complete',
            'thread-id': 'thread-secret-identifier',
            'turn-id': 'turn-secret-identifier',
            'cwd': '/home/jack/private-project',
            'input-messages': ['private prompt'],
            'last-assistant-message': 'private response',
        }
        result = self.run_helper('--notify', payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(self.notifications(), [
            ['--app-name=Codex', '--urgency=normal', 'Codex • Done']])
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name,
                         hashlib.sha256(b'thread-secret-identifier').hexdigest() + '.json')
        record = json.loads(records[0].read_text())
        self.assertEqual(set(record), {
            'version', 'event', 'observed_at', 'valid_until', 'tmux_pane', 'tty'})
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['event'], 'turn-complete')
        self.assertEqual(record['tmux_pane'], '%17')
        self.assertIsNone(record['tty'])
        self.assertLessEqual(record['observed_at'], int(time.time()))
        self.assertEqual(record['valid_until'] - record['observed_at'], 300)
        self.assertEqual(stat.S_IMODE(records[0].stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(records[0].parent.stat().st_mode), 0o700)

    def test_permission_hook_notifies_but_never_answers_the_request(self):
        payload = {
            'hook_event_name': 'PermissionRequest',
            'session_id': 'session-1',
            'turn_id': 'turn-1',
            'cwd': '/home/jack/private-project',
            'tool_name': 'Bash',
            'tool_input': {'command': 'private command', 'description': 'private reason'},
        }
        result = self.run_helper('--hook', payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '', 'empty stdout leaves approval to Codex')
        self.assertEqual(self.notifications(), [[
            '--app-name=Codex', '--urgency=critical', 'Codex • Needs attention']])
        record = json.loads(self.records()[0].read_text())
        self.assertEqual(record['event'], 'approval-requested')

    def test_unknown_or_malformed_input_is_ignored(self):
        cases = [
            (['--notify', '{}'], None),
            (['--notify', 'not-json'], None),
            (['--hook'], '{}'),
            (['--hook'], 'not-json'),
            (['--unexpected'], '{}'),
        ]
        for args, stdin in cases:
            with self.subTest(args=args, stdin=stdin):
                result = subprocess.run(
                    [sys.executable, str(HELPER), *args], input=stdin, text=True,
                    capture_output=True, env=self.env, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
        self.assertEqual(self.notifications(), [])
        self.assertEqual(self.records(), [])

    def test_expired_record_is_removed_on_the_next_event(self):
        oldbook = self.runtime / 'oldbook'
        oldbook.mkdir(mode=0o700)
        events = oldbook / 'codex-events'
        events.mkdir(mode=0o700)
        expired = events / ('a' * 64 + '.json')
        expired.write_text(json.dumps({'valid_until': int(time.time()) - 1}))
        expired.chmod(0o600)
        result = self.run_helper('--notify', {
            'type': 'agent-turn-complete', 'thread-id': 'current'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(expired.exists())
        self.assertEqual(len(self.records()), 1)

    def test_new_user_prompt_clears_that_sessions_recent_event(self):
        completed = self.run_helper('--notify', {
            'type': 'agent-turn-complete', 'thread-id': 'session-1'})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(self.records()), 1)
        cleared = self.run_helper('--hook', {
            'hook_event_name': 'UserPromptSubmit',
            'session_id': 'session-1',
            'turn_id': 'turn-2',
            'prompt': 'private new prompt',
        })
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertEqual(cleared.stdout, '')
        self.assertEqual(self.records(), [])
        self.assertEqual(len(self.notifications()), 1,
                         'clearing routing metadata must not create a notification')


class CodexNotificationInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-codex-install-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.codex = self.home / '.codex'
        self.codex.mkdir(parents=True)
        self.helper = self.home / '.local/bin/oldbook-codex-notify'
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

    def test_install_preserves_config_and_existing_hooks_while_adding_callbacks(self):
        original_config = (
            'model = "gpt-6-astra"\n'
            '[tui]\nterminal_title = ["activity", "project-name"]\n')
        self.codex.joinpath('config.toml').write_text(original_config)
        existing = {
            'description': 'Keep this description',
            'hooks': {'SessionStart': [{'hooks': [
                {'type': 'command', 'command': '/bin/existing'}]}]},
            'extension': {'keep': True},
        }
        self.codex.joinpath('hooks.json').write_text(json.dumps(existing, indent=2) + '\n')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.codex.joinpath('config.toml').read_text()
        self.assertEqual(config, 'notify = [' + json.dumps(str(self.helper))
                         + ', "--notify"]\n' + original_config)
        hooks = json.loads(self.codex.joinpath('hooks.json').read_text())
        self.assertEqual(hooks['description'], existing['description'])
        self.assertEqual(hooks['extension'], existing['extension'])
        self.assertEqual(hooks['hooks']['SessionStart'], existing['hooks']['SessionStart'])
        permission = hooks['hooks']['PermissionRequest']
        self.assertEqual(len(permission), 1)
        handler = permission[0]['hooks'][0]
        self.assertEqual(handler, {
            'type': 'command', 'command': str(self.helper) + ' --hook',
            'timeout': 3, 'async': True})
        prompt = hooks['hooks']['UserPromptSubmit']
        self.assertEqual(len(prompt), 1)
        self.assertEqual(prompt[0]['hooks'][0], handler)
        backup = Path(result.stdout.strip())
        self.assertTrue(backup.is_dir())
        self.assertEqual(backup.joinpath('config.toml').read_text(), original_config)
        self.assertEqual(json.loads(backup.joinpath('hooks.json').read_text()), existing)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)

    def test_existing_notify_refuses_without_changing_either_file(self):
        config = 'notify = ["/bin/existing"]\nmodel = "gpt-6-astra"\n'
        hooks = {'hooks': {}}
        self.codex.joinpath('config.toml').write_text(config)
        self.codex.joinpath('hooks.json').write_text(json.dumps(hooks))
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('existing notify', result.stderr)
        self.assertEqual(self.codex.joinpath('config.toml').read_text(), config)
        self.assertEqual(json.loads(self.codex.joinpath('hooks.json').read_text()), hooks)

    def test_broken_config_symlink_is_never_replaced(self):
        config = self.codex / 'config.toml'
        config.symlink_to(self.home / 'missing-config')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('non-regular file', result.stderr)
        self.assertTrue(config.is_symlink())
        self.assertEqual(os.readlink(config), str(self.home / 'missing-config'))
        self.assertFalse(self.codex.joinpath('hooks.json').exists())

    def test_rollback_restores_exact_files_and_removes_new_hooks_file(self):
        original_config = 'model = "gpt-6-astra"\n'
        self.codex.joinpath('config.toml').write_text(original_config)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        rollback = subprocess.run(
            [sys.executable, str(INSTALLER), '--target', str(self.home),
             '--rollback', str(backup)], text=True, capture_output=True, timeout=5)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        self.assertEqual(self.codex.joinpath('config.toml').read_text(), original_config)
        self.assertFalse(self.codex.joinpath('hooks.json').exists())

    def test_rollback_refuses_if_installed_files_were_changed(self):
        self.codex.joinpath('config.toml').write_text('model = "gpt-6-astra"\n')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = Path(result.stdout.strip())
        self.codex.joinpath('config.toml').write_text('user change\n')
        rollback = subprocess.run(
            [sys.executable, str(INSTALLER), '--target', str(self.home),
             '--rollback', str(backup)], text=True, capture_output=True, timeout=5)
        self.assertNotEqual(rollback.returncode, 0)
        self.assertIn('changed since installation', rollback.stderr)
        self.assertEqual(self.codex.joinpath('config.toml').read_text(), 'user change\n')


if __name__ == '__main__':
    unittest.main()
