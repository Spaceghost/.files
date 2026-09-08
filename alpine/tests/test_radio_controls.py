"""Exercise the menu launcher through inert private doas/notification shims."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


loader = importlib.machinery.SourceFileLoader('radio_controls',
    str(Path(__file__).parents[1] / 'desktop/.local/bin/mbp-intel-control'))
spec = importlib.util.spec_from_loader(loader.name, loader)
control = importlib.util.module_from_spec(spec)
loader.exec_module(control)


class RadioControlsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root / 'commands.jsonl'
        self.cli = self.root / 'root-only-controller'
        self.cli.write_text('not executable by the desktop user\n')
        self.cli.chmod(0o640)
        for name in ('doas', 'notify-send', 'privacyctl'):
            shim = self.root / name
            shim.write_text(f'#!{sys.executable}\n' +
                'import json,os,sys\n' +
                'from pathlib import Path\n' +
                'with Path(os.environ["RADIO_TEST_LOG"]).open("a") as stream:\n' +
                '    stream.write(json.dumps([Path(sys.argv[0]).name,*sys.argv[1:]])+"\\n")\n' +
                'raise SystemExit(int(os.environ.get("RADIO_TEST_RESULT","0")) if Path(sys.argv[0]).name=="doas" else 0)\n')
            shim.chmod(0o755)
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, {'PATH': str(self.root), 'RADIO_TEST_LOG': str(self.log)}).start()
        mock.patch.object(control, 'PRIVACYCTL', self.cli, create=True).start()

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_nonexecutable_root_helper_uses_exact_doas_path(self):
        control.radio_off()
        self.assertEqual(self.commands(), [['doas', '-n', str(self.cli), 'off']])

    def test_missing_helper_does_not_use_a_path_replacement(self):
        self.cli.unlink()
        control.radio_off()
        commands = self.commands()
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], 'notify-send')
        self.assertIn('not installed', commands[0][-1])

    def test_failed_privileged_request_reports_failure(self):
        with mock.patch.dict(os.environ, {'RADIO_TEST_RESULT': '1'}):
            control.radio_off()
        commands = self.commands()
        self.assertEqual(commands[0], ['doas', '-n', str(self.cli), 'off'])
        self.assertEqual(commands[1][0], 'notify-send')
        self.assertIn('could not complete', commands[1][-1])


if __name__ == '__main__':
    unittest.main()
