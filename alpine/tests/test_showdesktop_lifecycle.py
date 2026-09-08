"""Hidden desktop recovery retains navigation and only falls back when bare."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import showdesktop


def workspace(identifier, name, output='ONE', focused=False, visible=False):
    number = name.partition(':')[0]
    return {'id': identifier, 'name': name, 'num': int(number) if number.isdecimal() else -1,
            'output': output, 'focused': focused, 'visible': visible}


class Lifecycle(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.sway = Path('/private/sway.sock')
        self.origin = workspace(1, '4: My renamed Café')
        self.desktop = workspace(2, 'desktop', focused=True, visible=True)
        self.destination = workspace(3, '5: Empty custom', focused=True, visible=True)
        self.ipc = {'request': Mock(return_value=[self.origin, self.desktop]), 'command': Mock()}
        self.state = {'version': showdesktop.STATE_VERSION, 'socket': str(self.sway),
                      'workspace_id': 1, 'workspace_num': 4, 'workspace': '4: Signal',
                      'output': 'ONE', 'hidden': True}

    def save(self):
        showdesktop.write_state(self.directory, self.state)
        (self.directory / 'capture.ppm').write_bytes(b'private capture fixture')

    def assert_cleared(self):
        self.assertFalse((self.directory / 'state.json').exists())
        self.assertFalse((self.directory / 'capture.ppm').exists())

    def test_external_same_output_destination_is_retained_without_detour(self):
        self.save()
        self.ipc['request'].return_value = [self.origin, self.destination]
        showdesktop.recover_state(self.ipc, self.sway, self.directory)
        self.ipc['command'].assert_not_called()
        self.assert_cleared()

    def test_hidden_origin_is_found_by_id_after_rename(self):
        self.save()
        showdesktop.recover_state(self.ipc, self.sway, self.directory)
        self.ipc['command'].assert_called_once_with(self.sway, 'workspace "4: My renamed Café"')
        self.assert_cleared()

    def test_other_output_restores_origin_and_retains_requested_custom_destination(self):
        self.save()
        self.desktop['focused'] = False
        self.destination['output'] = 'TWO'
        self.ipc['request'].return_value = [self.origin, self.desktop, self.destination]
        showdesktop.recover_state(self.ipc, self.sway, self.directory)
        self.ipc['command'].assert_called_once_with(
            self.sway, 'workspace "4: My renamed Café"; workspace "5: Empty custom"')
        self.assert_cleared()

    def test_foreign_session_state_never_moves_this_session(self):
        self.state['socket'] = '/another/sway.sock'
        self.save()
        showdesktop.recover_state(self.ipc, self.sway, self.directory)
        self.ipc['request'].assert_not_called()
        self.ipc['command'].assert_not_called()
        self.assert_cleared()

    def test_missing_origin_returns_to_normal_numbered_workspace(self):
        self.save()
        self.ipc['request'].return_value = [self.desktop]
        showdesktop.recover_state(self.ipc, self.sway, self.directory)
        self.ipc['command'].assert_called_once_with(self.sway, 'workspace number "4: Signal"')
        self.assert_cleared()

    def test_failed_recovery_retains_state_for_retry(self):
        self.save()
        self.ipc['command'].side_effect = OSError('temporary IPC failure')
        with self.assertRaises(OSError):
            showdesktop.recover_state(self.ipc, self.sway, self.directory)
        self.assertTrue((self.directory / 'state.json').is_file())
        self.assertTrue((self.directory / 'capture.ppm').is_file())

    def test_own_hide_and_restore_focus_events_do_not_cancel(self):
        self.save()
        session = showdesktop.DesktopSession(self.ipc, self.sway, self.directory)
        session.active, session.cancel = True, Mock()
        session.expect({'name': 'desktop'})
        session.focused(self.desktop)
        session.expect({'id': self.origin['id']})
        session.focused(self.origin)
        session.cancel.assert_not_called()
        self.assertFalse(session.navigation)
        self.assertEqual(session.expected, [])

    def test_external_focus_cancels_active_pass_before_recovery(self):
        self.save()
        session = showdesktop.DesktopSession(self.ipc, self.sway, self.directory)
        session.active, session.cancel = True, Mock()
        session.focused(self.destination)
        session.cancel.assert_called_once()
        self.assertTrue(session.cancelled)
        self.assertTrue((self.directory / 'state.json').is_file())
        self.assertFalse(session.swap('workspace desktop', {'name': 'desktop'}))
        self.ipc['command'].assert_not_called()
        self.ipc['request'].return_value = [self.origin, self.destination]
        session.active = False
        session.finish()
        self.assert_cleared()

    def test_pending_origin_focus_before_hide_does_not_cancel(self):
        self.state['hidden'] = False
        self.save()
        session = showdesktop.DesktopSession(self.ipc, self.sway, self.directory)
        session.active, session.cancel = True, Mock()
        session.focused(self.origin)
        session.cancel.assert_not_called()

    def test_external_focus_recovers_an_idle_hidden_session_immediately(self):
        self.save()
        self.ipc['request'].return_value = [self.origin, self.destination]
        session = showdesktop.DesktopSession(self.ipc, self.sway, self.directory)
        session.focused(self.destination)
        self.assert_cleared()
        self.assertFalse(session.navigation)

    def test_restore_without_hidden_state_does_not_open_carousel(self):
        self.ipc['request'].return_value = [self.destination]
        with patch.object(showdesktop, 'launch_carousel') as carousel, patch.object(showdesktop, 'animate') as animate:
            showdesktop.perform('restore', self.ipc, self.sway, self.directory)
        carousel.assert_not_called()
        animate.assert_not_called()

    def test_return_gesture_without_hidden_state_opens_carousel_once(self):
        self.ipc['request'].return_value = [self.destination]
        with patch.object(showdesktop, 'launch_carousel') as carousel, patch.object(showdesktop, 'animate') as animate:
            showdesktop.perform('restore-or-carousel', self.ipc, self.sway, self.directory)
        carousel.assert_called_once_with()
        animate.assert_not_called()

    def test_return_gesture_restores_hidden_windows_without_carousel(self):
        self.save()
        with patch.object(showdesktop, 'has_hidden_windows', return_value=True), \
                patch.object(showdesktop, 'launch_carousel') as carousel, \
                patch.object(showdesktop, 'animate', return_value=True) as animate:
            showdesktop.perform('restore-or-carousel', self.ipc, self.sway, self.directory)
        self.assertTrue(animate.call_args.kwargs['restoring'])
        carousel.assert_not_called()
        self.assert_cleared()

    def test_lost_capture_restores_real_windows_without_animation(self):
        self.save()
        (self.directory / 'capture.ppm').unlink()
        with patch.object(showdesktop, 'has_hidden_windows', return_value=True), \
                patch.object(showdesktop, 'launch_carousel') as carousel, patch.object(showdesktop, 'animate') as animate:
            showdesktop.perform('restore-or-carousel', self.ipc, self.sway, self.directory)
        self.ipc['command'].assert_called_once_with(self.sway, 'workspace "4: My renamed Café"')
        animate.assert_not_called()
        carousel.assert_not_called()
        self.assert_cleared()

    def test_closed_hidden_windows_release_state_and_open_carousel(self):
        self.save()
        with patch.object(showdesktop, 'has_hidden_windows', return_value=False), \
                patch.object(showdesktop, 'launch_carousel') as carousel, patch.object(showdesktop, 'animate') as animate:
            showdesktop.perform('restore-or-carousel', self.ipc, self.sway, self.directory)
        carousel.assert_called_once_with()
        animate.assert_not_called()
        self.assert_cleared()

    def test_failed_animation_attempts_recovery(self):
        self.save()
        with patch.object(showdesktop, 'has_hidden_windows', return_value=True), \
                patch.object(showdesktop, 'animate', side_effect=RuntimeError('overlay failed')):
            with self.assertRaisesRegex(RuntimeError, 'overlay failed'):
                showdesktop.perform('restore', self.ipc, self.sway, self.directory)
        self.ipc['command'].assert_called_once_with(self.sway, 'workspace "4: My renamed Café"')
        self.assert_cleared()

    def test_cold_return_is_still_restore_after_startup_recovery(self):
        self.save()
        child = Mock()
        child.poll.return_value = 0
        with patch.dict(showdesktop.os.environ, {'XDG_RUNTIME_DIR': str(self.directory)}), \
                patch.object(showdesktop, 'private_directory', return_value=self.directory), \
                patch.object(showdesktop, 'session_socket', return_value=self.sway), \
                patch.object(showdesktop, 'has_hidden_windows', return_value=True), \
                patch.object(showdesktop, 'load_ipc', return_value=self.ipc), \
                patch.object(showdesktop, 'deliver', side_effect=[False, False, True]) as deliver, \
                patch.object(showdesktop.subprocess, 'Popen', return_value=child) as spawn, \
                patch.object(showdesktop.time, 'sleep'):
            showdesktop.run('restore-or-carousel')
        self.assertEqual(deliver.call_args.args[1], 'restore')
        spawn.assert_called_once()


if __name__ == '__main__':
    unittest.main()
