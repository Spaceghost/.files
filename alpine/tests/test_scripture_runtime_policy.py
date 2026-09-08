"""The public CLI must refuse local inference before touching its runtime."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
COMMAND = REPO / 'alpine/desktop/.local/bin/mbp-intel-scripture-local'


class ScriptureRuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='scripture-runtime-policy-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'config/mbp-intel/ollama.json'
        self.runtime = self.root / 'data/mbp-intel/ollama/runtime-0.17.7-r1/usr/bin/ollama'
        self.runtime.parent.mkdir(parents=True)
        (self.root / 'data/mbp-intel/ollama/models').mkdir()
        self.marker = self.root / 'server-was-invoked'
        # A harmless canary makes accidental backend launch observable. It
        # neither loads a model nor opens a server.
        self.runtime.write_text('#!/bin/sh\nprintf attempted > '
                                + shlex.quote(str(self.marker)) + '\nexit 1\n')
        self.runtime.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'),
                        XDG_STATE_HOME=str(self.root / 'state'))

    def configure(self, policy):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps(policy))

    def command(self, *arguments):
        return subprocess.run([sys.executable, '-I', str(COMMAND), *arguments], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def assert_denied(self):
        result = self.command('John 1:1', '--kind', 'observation')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Alienware', result.stderr)
        self.assertIn('disabled', result.stderr)
        self.assertFalse(self.marker.exists(), 'The disabled local backend was invoked')
        self.assertFalse((self.root / 'state').exists(), 'Disabled inference created runtime state')

    def test_missing_policy_denies_before_starting_any_backend(self):
        self.assert_denied()

    def test_alienware_policy_disables_local_runtime(self):
        self.configure({'local_server_enabled': False, 'inference_host': 'alienware'})
        self.assert_denied()

    def test_truthy_values_or_alienware_selection_cannot_enable_local_runtime(self):
        for policy in ({}, [], {'local_server_enabled': 'true', 'inference_host': 'local'},
                       {'local_server_enabled': 1, 'inference_host': 'local'},
                       {'local_server_enabled': True, 'inference_host': 'alienware'}):
            with self.subTest(policy=policy):
                self.configure(policy)
                self.assert_denied()

    def test_invalid_policy_denies_without_runtime_state(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text('{invalid json')
        self.assert_denied()

    def test_help_remains_available_without_opt_in(self):
        result = self.command('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--model', result.stdout)
        self.assertFalse(self.marker.exists())
        self.assertFalse((self.root / 'state').exists())

    def test_explicit_local_opt_in_reaches_existing_runtime_validation(self):
        self.configure({'local_server_enabled': True, 'inference_host': 'local'})
        self.runtime.unlink()
        result = self.command('John 1:1', '--kind', 'observation')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('runtime is missing', result.stderr)
        self.assertFalse(self.marker.exists())


if __name__ == '__main__':
    unittest.main()
