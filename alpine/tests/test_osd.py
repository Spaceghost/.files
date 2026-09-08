"""On-screen feedback tests: message validation, fade timing and quiet clients.

Nothing here needs a display. The daemon's drawing is exercised separately by
`oldbook-osd preview`, which renders the pill to a PNG through the same code.
"""
import json
import os
from pathlib import Path
import runpy
import shlex
import socket
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import osd  # noqa: E402

BIN = REPO / 'alpine/desktop/.local/bin'
HELPER = BIN / 'oldbook-osd'


class MessageTests(unittest.TestCase):
    def test_show_and_flash_round_trip(self):
        for kind in osd.KINDS:
            request = osd.parse_message(osd.show_message(kind, 42, muted=kind.endswith('mute')))
            self.assertEqual(request, {'action': 'show', 'kind': kind, 'value': 42,
                                       'muted': kind.endswith('mute')})
        self.assertEqual(osd.parse_message(osd.flash_message()), {'action': 'flash'})

    def test_values_are_clamped_by_the_client_and_rejected_by_the_daemon(self):
        self.assertEqual(osd.parse_message(osd.show_message('volume', 999))['value'], osd.MAX_VALUE)
        self.assertEqual(osd.parse_message(osd.show_message('volume', -5))['value'], 0)
        with self.assertRaises(ValueError):
            osd.show_message('coffee', 10)
        for garbage in [b'', b'{', b'[]', b'null', b'"show"', json.dumps({'action': 'show'}).encode(),
                        json.dumps({'action': 'show', 'kind': 'coffee', 'value': 1}).encode(),
                        json.dumps({'action': 'show', 'kind': 'volume', 'value': '1'}).encode(),
                        json.dumps({'action': 'show', 'kind': 'volume', 'value': True}).encode(),
                        json.dumps({'action': 'show', 'kind': 'volume', 'value': 151}).encode(),
                        json.dumps({'action': 'show', 'kind': 'volume', 'value': -1}).encode(),
                        json.dumps({'action': 'show', 'kind': 'volume', 'value': 1,
                                    'muted': 'yes'}).encode(),
                        json.dumps({'action': 'reboot'}).encode(),
                        b'{"action": "flash", "padding": "' + b'x' * osd.MAX_MESSAGE + b'"}',
                        'not bytes']:
            self.assertIsNone(osd.parse_message(garbage), garbage)

    def test_glyphs_and_labels_follow_level_and_mute(self):
        low, medium, high = (osd.describe('volume', value) for value in (10, 50, 90))
        self.assertEqual([low['glyph'], medium['glyph'], high['glyph']],
                         [osd.GLYPHS['volume-low'], osd.GLYPHS['volume-medium'],
                          osd.GLYPHS['volume-high']])
        self.assertEqual(low['label'], 'Volume')
        muted = osd.describe('mute', 40, muted=True)
        self.assertEqual((muted['glyph'], muted['label'], muted['muted']),
                         (osd.GLYPHS['volume-off'], 'Muted', True))
        self.assertEqual(osd.describe('mute', 40)['label'], 'Sound on')
        self.assertEqual(osd.describe('mic-mute', 100, muted=True)['label'], 'Microphone off')
        self.assertEqual(osd.describe('mic', 100)['glyph'], osd.GLYPHS['mic'])
        self.assertEqual(osd.describe('brightness', 65)['label'], 'Brightness')
        self.assertEqual(osd.describe('keyboard', 30)['label'], 'Keyboard light')
        boosted = osd.describe('volume', 120)
        self.assertEqual((boosted['fill'], boosted['boosted'], boosted['value']), (1.0, True, 120))
        self.assertAlmostEqual(osd.describe('volume', 25)['fill'], 0.25)
        with self.assertRaises(ValueError):
            osd.describe('coffee', 1)


class TimingTests(unittest.TestCase):
    def test_pill_holds_then_fades_to_exactly_zero_without_overshoot(self):
        feedback = osd.Feedback(hold_ms=1000, fade_ms=200)
        self.assertEqual(feedback.alpha_at(0), 0.0)
        feedback.show({'label': 'Volume'}, 5000)
        self.assertTrue(feedback.visible)
        self.assertEqual(feedback.alpha_at(5000), 1.0)
        self.assertEqual(feedback.alpha_at(5999), 1.0)
        self.assertEqual(feedback.fade_starts_at(), 6000)
        samples = [feedback.alpha_at(6000 + step * 20) for step in range(11)]
        self.assertEqual(samples[0], 1.0)
        self.assertEqual(samples[-1], 0.0)
        self.assertEqual(samples, sorted(samples, reverse=True))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in samples))
        self.assertEqual(feedback.alpha_at(9000), 0.0)
        self.assertTrue(feedback.hidden_at(6200))
        self.assertFalse(feedback.hidden_at(6199))

    def test_new_reading_during_the_fade_snaps_back_to_full_opacity(self):
        feedback = osd.Feedback(hold_ms=1000, fade_ms=200)
        feedback.show({'label': 'Volume'}, 0)
        self.assertLess(feedback.alpha_at(1100), 1.0)
        feedback.show({'label': 'Brightness'}, 1100)
        self.assertEqual(feedback.alpha_at(1100), 1.0)
        self.assertEqual(feedback.content['label'], 'Brightness')
        feedback.hide()
        self.assertFalse(feedback.visible)
        self.assertEqual(feedback.alpha_at(1100), 0.0)

    def test_disabled_animations_skip_the_fade_and_the_flash(self):
        feedback = osd.Feedback(hold_ms=1000, fade_ms=200, animate=False)
        feedback.show({}, 0)
        self.assertEqual(feedback.alpha_at(999), 1.0)
        self.assertEqual(feedback.alpha_at(1000), 0.0)
        self.assertTrue(feedback.hidden_at(1000))
        self.assertEqual(osd.Flash(0, animate=False).alpha_at(0), 0.0)
        with self.assertRaises(ValueError):
            osd.Feedback(hold_ms=-1)
        with self.assertRaises(ValueError):
            osd.Feedback(fade_ms=0)

    def test_flash_starts_bright_and_is_gone_after_its_duration(self):
        flash = osd.Flash(1000, duration_ms=120, peak=0.85)
        self.assertEqual(flash.alpha_at(1000), 0.85)
        self.assertAlmostEqual(flash.alpha_at(1060), 0.425)
        self.assertEqual(flash.alpha_at(1120), 0.0)
        self.assertEqual(flash.alpha_at(2000), 0.0)
        self.assertTrue(flash.finished_at(1120))
        self.assertFalse(flash.finished_at(1119))
        # A frame timestamp from just before the request still reads as the peak.
        self.assertEqual(flash.alpha_at(999), 0.85)
        with self.assertRaises(ValueError):
            osd.Flash(0, peak=0)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-osd-test-')
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name)
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.runtime))
        self.env.pop('SWAYSOCK', None)

    def run_helper(self, *arguments):
        return subprocess.run([sys.executable, str(HELPER), *arguments], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def test_client_is_quiet_and_starts_nothing_without_a_daemon(self):
        self.assertFalse(osd.send(osd.flash_message(), self.runtime))
        for arguments in (['show', '--kind', 'volume', '--value', '5'], ['flash']):
            result = self.run_helper(*arguments)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertFalse(list(self.runtime.iterdir()), 'the client must not create runtime state')
        self.assertNotEqual(self.run_helper('show', '--kind', 'coffee', '--value', '5').returncode, 0)
        self.assertNotEqual(self.run_helper('show', '--kind', 'volume').returncode, 0)

    def test_client_delivers_to_a_bound_daemon_socket(self):
        address = osd.endpoint(self.runtime)
        address.parent.mkdir(mode=0o700)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
            server.bind(str(address))
            server.settimeout(5)
            result = self.run_helper('show', '--kind', 'mic-mute', '--value', '77', '--muted')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(osd.parse_message(server.recv(4096)),
                             {'action': 'show', 'kind': 'mic-mute', 'value': 77, 'muted': True})
            self.assertEqual(self.run_helper('flash').returncode, 0)
            self.assertEqual(osd.parse_message(server.recv(4096)), {'action': 'flash'})
            self.assertTrue(osd.send(osd.show_message('keyboard', 200), self.runtime))
            self.assertEqual(osd.parse_message(server.recv(4096))['value'], osd.MAX_VALUE)

    def test_client_ignores_a_plain_file_at_the_socket_path(self):
        address = osd.endpoint(self.runtime)
        address.parent.mkdir(mode=0o700)
        address.write_text('not a socket\n')
        self.assertFalse(osd.send(osd.flash_message(), self.runtime))

    def test_daemon_refuses_a_session_outside_its_runtime_directory(self):
        module = runpy.run_path(str(HELPER))
        self.assertFalse(module['session_ready'](str(self.runtime)))
        foreign = Path(self.temp.name) / 'elsewhere'
        foreign.mkdir()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sway:
            sway.bind(str(foreign / 'sway-ipc.sock'))
            os.environ['SWAYSOCK'] = str(foreign / 'sway-ipc.sock')
            try:
                self.assertFalse(module['session_ready'](str(self.runtime)))
                self.assertTrue(module['session_ready'](str(foreign)))
            finally:
                os.environ.pop('SWAYSOCK', None)
        result = subprocess.run([sys.executable, str(HELPER), 'daemon'], env=self.env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual((result.returncode, result.stderr), (0, ''))

    def test_preview_renders_the_pill_without_a_display(self):
        output = self.runtime / 'pill.png'
        env = dict(self.env)
        env.pop('WAYLAND_DISPLAY', None)
        env.pop('DISPLAY', None)
        result = subprocess.run([sys.executable, str(HELPER), 'preview', '--kind', 'brightness',
                                 '--value', '65', '--output', str(output)], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Brightness 65%', result.stdout)
        self.assertEqual(output.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')


class HelperWiringTests(unittest.TestCase):
    """The key helpers report through the OSD and stay quiet when it is absent."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-osd-wiring-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stubs = self.root / 'bin'
        self.stubs.mkdir()
        self.log = self.root / 'calls.log'
        self.env = dict(os.environ, HOME=str(self.root), XDG_RUNTIME_DIR=str(self.root),
                        PATH=str(self.stubs) + os.pathsep + os.environ.get('PATH', ''))

    def stub(self, name, body):
        path = self.stubs / name
        path.write_text('#!/bin/sh\nprintf \'%s\\n\' "' + name + ' $*" >> '
                        + shlex.quote(str(self.log)) + '\n' + body)
        path.chmod(0o755)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_audio_helper_reports_the_new_level_and_mute_state(self):
        self.stub('wpctl', 'case "$1" in get-volume) printf \'Volume: 0.40 [MUTED]\\n\';; esac\n')
        self.stub('oldbook-osd', '')
        self.stub('notify-send', '')
        for action, kind in (('up', 'volume'), ('down', 'volume'), ('mute', 'mute'),
                             ('mic-mute', 'mic-mute')):
            self.log.unlink(missing_ok=True)
            result = subprocess.run([str(BIN / 'oldbook-audio'), action], env=self.env,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('oldbook-osd show --kind ' + kind + ' --value 40 --muted', self.calls())
        self.assertEqual([line for line in self.calls() if 'notify-send' in line], [])

    def test_audio_helper_rounds_unmuted_levels(self):
        self.stub('wpctl', 'case "$1" in get-volume) printf \'Volume: 0.65\\n\';; esac\n')
        self.stub('oldbook-osd', '')
        subprocess.run([str(BIN / 'oldbook-audio'), 'up'], env=self.env, check=True, timeout=20)
        self.assertIn('oldbook-osd show --kind volume --value 65', self.calls())
        self.assertNotIn('--muted', ''.join(self.calls()))

    def test_brightness_helper_reports_percent_through_the_osd(self):
        backlight = self.root / 'backlight/gmux_backlight'
        backlight.mkdir(parents=True)
        (backlight / 'brightness').write_text('500\n')
        (backlight / 'max_brightness').write_text('1000\n')
        self.stub('oldbook-osd', '')
        self.stub('notify-send', '')
        env = dict(self.env, OLDBOOK_BACKLIGHT_ROOT=str(self.root / 'backlight'))
        result = subprocess.run([str(BIN / 'oldbook-brightness'), 'up'], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((backlight / 'brightness').read_text().strip(), '550')
        self.assertIn('oldbook-osd show --kind brightness --value 55', self.calls())
        self.assertEqual([line for line in self.calls() if 'notify-send' in line], [])

    def test_brightness_helper_keeps_the_permission_notification(self):
        backlight = self.root / 'backlight/gmux_backlight'
        backlight.mkdir(parents=True)
        (backlight / 'brightness').write_text('500\n')
        (backlight / 'max_brightness').write_text('1000\n')
        (backlight / 'brightness').chmod(0o444)
        self.stub('oldbook-osd', '')
        self.stub('notify-send', '')
        env = dict(self.env, OLDBOOK_BACKLIGHT_ROOT=str(self.root / 'backlight'))
        result = subprocess.run([str(BIN / 'oldbook-brightness'), 'up'], env=env,
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(line.startswith('notify-send') and 'permission' in line
                            for line in self.calls()))
        self.assertFalse(any(line.startswith('oldbook-osd') for line in self.calls()))


if __name__ == '__main__':
    unittest.main()
