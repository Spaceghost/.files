"""CLI lifecycle boundaries that must not require GTK or affect real processes."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from superhold.shortcut_overlay import _request_running_guide, main


class CliLifecycleTests(unittest.TestCase):
    def test_starting_service_is_not_sent_default_terminating_usr1(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            path.write_text(json.dumps({'state': 'starting', 'process': {'pid': 123}}))
            with mock.patch('superhold.shortcut_overlay.os.kill') as kill:
                self.assertFalse(_request_running_guide(SimpleNamespace(status_path=path)))
            kill.assert_not_called()

    def test_ready_service_is_signalled_only_while_its_process_identity_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            process = {'pid': 123, 'start_time': 'same-process'}
            path.write_text(json.dumps({'state': 'running', 'process': process}))
            with mock.patch('superhold.shortcut_overlay._process_identity', return_value=process), \
                    mock.patch('superhold.shortcut_overlay.os.kill') as kill:
                self.assertTrue(_request_running_guide(SimpleNamespace(status_path=path)))
                kill.assert_called_once_with(123, signal.SIGUSR1)
            with mock.patch('superhold.shortcut_overlay._process_identity', return_value=None), \
                    mock.patch('superhold.shortcut_overlay.os.kill') as kill:
                self.assertFalse(_request_running_guide(SimpleNamespace(status_path=path)))
                kill.assert_not_called()

    def test_status_still_works_when_settings_file_is_invalid(self):
        with mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': '/unused'}, clear=True), \
                mock.patch('superhold.config.load_config', side_effect=ValueError('invalid settings')), \
                mock.patch('superhold.shortcut_overlay._owned_private_directory'), \
                mock.patch('superhold.shortcut_overlay.find_sway_socket', return_value=Path('/unused/sway')), \
                mock.patch('superhold.shortcut_overlay.print_status') as status:
            main(['status'])
            status.assert_called_once_with(Path('/unused'), Path('/unused/sway'))

    def test_settings_command_is_independent_of_sway_and_runtime_socket(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch('superhold.settings.show_settings', return_value=0) as settings:
            self.assertEqual(main(['settings', '--config', '/unused/custom.json']), 0)
            settings.assert_called_once_with('/unused/custom.json')


if __name__ == '__main__':
    unittest.main()
