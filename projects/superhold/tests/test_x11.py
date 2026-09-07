"""X11 polling and configuration tests without touching a display or input."""
import json
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from superhold.hold import HoldState, KEY_CAPSLOCK, KEY_LEFTMETA
from superhold.service import (AlreadyRunning, GraphicalSessionGuard, SessionLease,
                                  probe_session, screensaver_locked)
from superhold.x11 import (X11Monitor, X11ShortcutProvider, display_identity,
                             lxqt_section, openbox_section, physical_trigger_codes)
from superhold.x11 import raw_key_event


class X11MonitorTests(unittest.TestCase):
    def test_xi2_raw_key_suffix_preserves_press_release_and_repeat_flag(self):
        event = SimpleNamespace(type=35, extension=131, evtype=13,
                                data=struct.pack('=HIIHHII', 3, 1234, 72, 7, 0, 0, 0))
        self.assertEqual(raw_key_event(event, 131), (72, 1, 7, False))
        event.evtype = 14
        self.assertEqual(raw_key_event(event, 131), (72, 0, 7, False))
        event.data = struct.pack('=HIIHHII', 3, 1234, 72, 7, 0, 1 << 16, 0)
        self.assertTrue(raw_key_event(event, 131)[3])
        self.assertIsNone(raw_key_event(event, 132))
        event.data = b'short'
        with self.assertRaises(RuntimeError):
            raw_key_event(event, 131)

    def test_physical_key_names_survive_caps_escape_remapping(self):
        reply = subprocess.CompletedProcess([], 0, '''xkb_keymap {
            xkb_keycodes "test" { <CAPS> = 72;
            <LWIN> = 130;
            <RWIN> = 131;
            };
            xkb_symbols "test" { key <CAPS> { [ Escape ] }; };
            };''', '')
        with mock.patch('superhold.x11.subprocess.run', return_value=reply) as run:
            codes = physical_trigger_codes(':938')
        self.assertEqual(codes[72], KEY_CAPSLOCK)
        self.assertEqual(codes[130], KEY_LEFTMETA)
        self.assertEqual(run.call_args.args[0], ['xkbcomp', '-xkb', ':938', '-'])

    def monitor(self, trigger='super'):
        result = X11Monitor(HoldState(trigger, .2), ':938', start=False)
        self.addCleanup(result.close)
        return result

    def test_held_startup_key_requires_release_before_it_can_trigger(self):
        monitor = self.monitor()
        monitor._enqueue({KEY_LEFTMETA}, 1)
        self.assertFalse(monitor.poll(1))
        monitor._enqueue({KEY_LEFTMETA}, 1.3)
        self.assertFalse(monitor.poll(1.3))
        monitor._enqueue(set(), 2)
        monitor.poll(2)
        monitor._enqueue({KEY_LEFTMETA}, 2.1)
        monitor.poll(2.1)
        monitor._enqueue({KEY_LEFTMETA}, 2.31)
        self.assertTrue(monitor.poll(2.31))

    def test_release_and_intermediate_chord_are_not_lost_between_gui_ticks(self):
        monitor = self.monitor()
        monitor._enqueue(set(), 0)
        monitor.poll(0)
        monitor._enqueue({KEY_LEFTMETA}, .1)
        monitor._enqueue({KEY_LEFTMETA, 1034}, .11)
        monitor._enqueue({KEY_LEFTMETA}, .12)
        monitor._enqueue({KEY_LEFTMETA}, .4)
        self.assertFalse(monitor.poll(.4))
        monitor._enqueue(set(), .41)
        self.assertFalse(monitor.poll(.41))

    def test_stale_connection_and_overflow_fail_closed_without_blocking(self):
        monitor = self.monitor()
        monitor._enqueue(set(), 0)
        monitor.poll(0)
        monitor._enqueue({KEY_LEFTMETA}, .1)
        monitor.poll(.1)
        monitor._enqueue({KEY_LEFTMETA}, .31)
        self.assertTrue(monitor.poll(.31))
        started = time.monotonic()
        self.assertFalse(monitor.poll(1))
        self.assertLess(time.monotonic() - started, .02)
        for index in range(300):
            monitor._enqueue({KEY_LEFTMETA}, 2 + index / 1000)
        self.assertFalse(monitor.poll(2.3))
        monitor._failed = True
        self.assertFalse(monitor.alive())
        self.assertFalse(monitor.poll(3))

    def test_capslock_release_and_screensaver_cancel_without_toggle_assumptions(self):
        monitor = self.monitor('capslock')
        monitor._enqueue(set(), 0)
        monitor.poll(0)
        monitor._enqueue({KEY_CAPSLOCK}, .1)
        monitor.poll(.1)
        monitor._enqueue({KEY_CAPSLOCK}, .31)
        self.assertTrue(monitor.poll(.31))
        monitor._enqueue({KEY_CAPSLOCK}, .32, locked=True)
        self.assertFalse(monitor.poll(.32))
        monitor._enqueue({KEY_CAPSLOCK}, .4, locked=False)
        self.assertFalse(monitor.poll(.4))
        monitor._enqueue(set(), .5)
        self.assertFalse(monitor.poll(.5))


class DesktopConfigTests(unittest.TestCase):
    def test_context_helper_ignores_a_shadow_package_in_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shadow = root / 'superhold'
            shadow.mkdir()
            marker = root / 'executed'
            (shadow / '__init__.py').write_text(
                'from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n')
            provider = X11ShortcutProvider(':193838')
            previous = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaises(RuntimeError):
                    provider.context()
            finally:
                os.chdir(previous)
            self.assertFalse(marker.exists())

    def test_openbox_namespaces_chains_and_actions_are_read_only_and_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rc.xml'
            marker = Path(directory) / 'must-not-exist'
            path.write_text(f'''<openbox_config xmlns="http://openbox.org/3.4/rc"><keyboard>
                <keybind key="W-Return"><action name="Execute"><command>touch {marker}</command></action></keybind>
                <keybind key="C-x"><keybind key="C-c"><action name="Close"/></keybind></keybind>
                <keybind key="A-F4"/><keybind><action name="Close"/></keybind>
                </keyboard><mouse><keybind key="bad"><action name="Bad"/></keybind></mouse></openbox_config>''')
            result = openbox_section(path)
            self.assertEqual([row['key'] for row in result['rows']], ['Super+Enter', 'Ctrl+x, Ctrl+c'])
            self.assertIn(str(marker), result['rows'][0]['description'])
            self.assertFalse(marker.exists())
            self.assertTrue(result['coverage'].startswith('Partial'))
            self.assertIn(str(path), result['coverage'])

    def test_xml_entities_and_oversize_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rc.xml'
            for text in ('<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>', 'a' * (256 * 1024 + 1)):
                path.write_text(text)
                result = openbox_section(path)
                self.assertEqual(result['rows'], [])
                self.assertTrue(result['coverage'].startswith('Unavailable'))

    def test_fifo_configuration_is_rejected_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config-fifo'
            os.mkfifo(path)
            started = time.monotonic()
            for provider in (openbox_section, lxqt_section):
                result = provider(path)
                self.assertEqual(result['rows'], [])
                self.assertTrue(result['coverage'].startswith('Unavailable'))
            self.assertLess(time.monotonic() - started, .1)

    def test_lxqt_schema_enabled_actions_and_percent_encoded_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'globalkeyshortcuts.conf'
            path.write_text('''[General]
                AllowGrabLocks=false
                [Control%2BAlt%2BDelete.1]
                Enabled=true
                Comment=Session controls
                Exec=must-not-run, --argument
                [Super_L.2]
                Enabled=false
                Exec=hidden
                [Control+F.3]
                service=org.example.App
                path=/org/example/App
                interface=org.example.App
                method=Search
                [Alt+F2.4]
                Comment=Not a genuine action
                [Alt+F3.5]
                path=/registered/client
                Comment=Client shortcut
                ''')
            result = lxqt_section(path)
            self.assertEqual(result['rows'], [
                {'key': 'Control+Alt+Delete', 'description': 'Session controls'},
                {'key': 'Control+F', 'description': 'DBus: Search'},
                {'key': 'Alt+F3', 'description': 'Client shortcut'}])
            self.assertTrue(result['coverage'].startswith('Partial'))
            self.assertIn(str(path), result['coverage'])

    def test_x11_context_reuses_custom_profiles_and_dynamic_trigger_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profiles.json'
            path.write_text(json.dumps({'profiles': {'demo': {
                'name': 'Demo', 'aliases': ['DemoClass'], 'coverage': 'Partial local profile',
                'rows': [{'key': 'Ctrl+S', 'description': 'Save'}]}}}))
            provider = X11ShortcutProvider(':938', path, 'Caps Lock')
            context = {'window': {'app_id': 'DemoClass', 'pid': None}, 'output': 'test',
                       '_output_rect': {'x': 0, 'y': 0, 'width': 900, 'height': 600}}
            with mock.patch.object(provider, 'context', return_value=context), mock.patch.object(
                    provider, '_desktop_sections', return_value=[]):
                snapshot = provider.snapshot()
            self.assertEqual(snapshot['app'], 'Demo')
            self.assertEqual(snapshot['_output_rect'], context['_output_rect'])
            self.assertEqual(snapshot['sections'][-1]['rows'][0]['key'], 'Caps Lock (hold)')


class SessionTests(unittest.TestCase):
    def test_singleton_is_per_server_and_screen_aliases_do_not_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            one = SessionLease(runtime, display=':938')
            two = SessionLease(runtime, display='unix:938.1')
            other = SessionLease(runtime, display=':939')
            self.addCleanup(one.close)
            self.addCleanup(two.close)
            self.addCleanup(other.close)
            self.assertEqual(one.socket_id, two.socket_id)
            self.assertNotEqual(one.socket_id, other.socket_id)
            one.acquire()
            with self.assertRaises(AlreadyRunning):
                two.acquire()
            other.acquire()
            other.close()
            one.close()
        for display in (None, '', 'garbage', ':x', ':1\n', '/tmp/socket'):
            with self.subTest(display=display), self.assertRaises(ValueError):
                display_identity(display)

    def test_logind_lock_and_unknown_hint_are_conservative(self):
        with mock.patch.dict(os.environ, {'XDG_SESSION_ID': 'test'}), mock.patch(
                'superhold.service.screensaver_locked', return_value=False):
            for hint, expected in (('yes', True), ('no', False), ('', True)):
                reply = subprocess.CompletedProcess([], 0,
                    f'Active=yes\nState=active\nType=x11\nLockedHint={hint}\n', '')
                with mock.patch('superhold.service.subprocess.run', return_value=reply):
                    result = probe_session('x11', Path('/tmp'))
                self.assertTrue(result['active'])
                self.assertEqual(result['locked'], expected)

    def test_screensaver_queries_unique_owner_without_activating_missing_service(self):
        missing = subprocess.CompletedProcess([], 1, '', 'org.freedesktop.DBus.Error.NameHasNoOwner')
        owner = subprocess.CompletedProcess([], 0, 'string ":1.27"', '')
        locked = subprocess.CompletedProcess([], 0, 'boolean true', '')
        with mock.patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'test'}):
            with mock.patch('superhold.service.subprocess.run', return_value=missing) as run:
                self.assertFalse(screensaver_locked())
                self.assertTrue(all('org.freedesktop.DBus.GetNameOwner' in call.args[0]
                                    for call in run.call_args_list))
            with mock.patch('superhold.service.subprocess.run', side_effect=[owner, locked]) as run:
                self.assertTrue(screensaver_locked())
                self.assertIn('--dest=:1.27', run.call_args_list[-1].args[0])

    def test_slow_session_probe_expires_old_success_without_blocking_ui(self):
        pending = mock.Mock()
        pending.done.return_value = False
        guard = GraphicalSessionGuard('/tmp', '/tmp/socket',
                                      activity_probe=lambda: True, lock_probe=lambda *_: False)
        self.addCleanup(guard.close)
        guard._future = pending
        guard._active = True
        guard._checked_at = 1
        self.assertTrue(guard.allows_overlay(1.1))
        self.assertFalse(guard.allows_overlay(2.1))


if __name__ == '__main__':
    unittest.main()
