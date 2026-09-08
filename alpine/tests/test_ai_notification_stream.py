"""AI notification stream tests use an isolated session bus."""
import json
import os
from pathlib import Path
import runpy
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

STREAM = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-ai-notification-stream'


class AINotificationAttributionTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(STREAM))
        self.source_for = self.module['source_for']

    def test_exact_native_names_and_desktop_entries_are_attributed(self):
        cases = [
            ('Codex', {}, 'codex'),
            ('Claude', {}, 'claude'),
            ('ChatGPT', {}, 'chatgpt'),
            ('helper', {'desktop-entry': 'com.openai.codex'}, 'codex'),
            ('helper', {'desktop-entry': 'com.anthropic.claude'}, 'claude'),
            ('helper', {'desktop-entry': 'com.openai.chatgpt'}, 'chatgpt'),
        ]
        for app_name, hints, expected in cases:
            with self.subTest(app_name=app_name, hints=hints):
                self.assertEqual(self.source_for(app_name, hints), expected)

        for app_name in ('My Codex Notes', 'Claude-ish', 'ChatGPT reminder'):
            with self.subTest(app_name=app_name):
                self.assertIsNone(self.source_for(app_name, {}))

    def test_browser_requires_an_exact_identity_and_validated_origin_hint(self):
        valid = [
            ('Firefox', 'chatgpt.com', 'chatgpt'),
            ('Mozilla Firefox', 'https://chat.openai.com/', 'chatgpt'),
            ('Chromium', 'claude.ai', 'claude'),
            ('Google Chrome', 'https://claude.ai/', 'claude'),
        ]
        for browser, origin, expected in valid:
            with self.subTest(browser=browser, origin=origin):
                self.assertEqual(
                    self.source_for(browser, {'x-kde-origin-name': origin}),
                    expected,
                )

        invalid = [
            ('Firefox', {}),
            ('Firefox', {'x-kde-origin-name': 'evil-chatgpt.com'}),
            ('Firefox', {'x-kde-origin-name': 'https://chatgpt.com.evil.test/'}),
            ('Firefox', {'x-kde-origin-name': 'https://user@chatgpt.com/'}),
            ('Firefox', {'origin': 'chatgpt.com'}),
            ('Calendar', {'x-kde-origin-name': 'chatgpt.com'}),
        ]
        for browser, hints in invalid:
            with self.subTest(browser=browser, hints=hints):
                self.assertIsNone(self.source_for(browser, hints))


class AINotificationBusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-ai-bus-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.processes = []
        self.addCleanup(self.stop_processes)
        self.bus = subprocess.Popen(
            ['dbus-daemon', '--session', '--nofork', '--print-address'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.processes.append(self.bus)
        address = self.bus.stdout.readline().strip()
        self.assertTrue(address)
        self.env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address)
        self.count = self.root / 'delivered-count'
        server_code = r'''
import os
from pathlib import Path
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
name = dbus.service.BusName('org.freedesktop.Notifications', bus=bus, do_not_queue=True)
count_path = Path(os.environ['DELIVERED_COUNT'])
count = 0

class Notifications(dbus.service.Object):
    @dbus.service.method('org.freedesktop.Notifications', in_signature='susssasa{sv}i', out_signature='u')
    def Notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, timeout):
        global count
        count += 1
        count_path.write_text(str(count))
        return dbus.UInt32(count)

    @dbus.service.method('org.freedesktop.Notifications', in_signature='', out_signature='as')
    def GetCapabilities(self):
        return ['body', 'x-kde-origin-name']

    @dbus.service.method('org.freedesktop.Notifications', in_signature='', out_signature='ssss')
    def GetServerInformation(self):
        return ('mbp-intel-test', 'mbp-intel', '1', '1.3')

    @dbus.service.method('org.freedesktop.Notifications', in_signature='u', out_signature='')
    def CloseNotification(self, identifier):
        pass

Notifications(bus, '/org/freedesktop/Notifications')
print('ready', flush=True)
GLib.MainLoop().run()
'''
        server_env = dict(self.env, DELIVERED_COUNT=str(self.count))
        self.server = subprocess.Popen(
            [sys.executable, '-c', server_code],
            env=server_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.processes.insert(0, self.server)
        self.assertEqual(self.server.stdout.readline().strip(), 'ready')

    def stop_processes(self):
        for process in self.processes:
            if process.poll() is not None:
                continue
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.communicate(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=3)
                except ProcessLookupError:
                    pass

    def notify(self, app_name, hints=None):
        argv = ['notify-send', '--app-name=' + app_name]
        for hint in hints or []:
            argv.extend(['--hint', hint])
        argv.extend(['private title', 'body may mention Codex Claude ChatGPT'])
        completed = subprocess.run(argv, env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_stream_is_passive_content_free_and_preserves_normal_delivery(self):
        stream = subprocess.Popen(
            [str(STREAM)],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.processes.insert(0, stream)

        first_line = ''
        for _ in range(20):
            self.notify('Codex')
            if select.select([stream.stdout], [], [], .1)[0]:
                first_line = stream.stdout.readline()
                break
        self.assertTrue(first_line, 'stream did not observe the private bus')
        delivered_before = int(self.count.read_text())
        self.notify('Calendar')
        self.notify('Claude')
        self.notify('Firefox', ['string:x-kde-origin-name:chatgpt.com'])
        self.notify('Firefox', ['string:x-kde-origin-name:example.com'])

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.count.exists() and int(self.count.read_text()) == delivered_before + 4:
                break
            time.sleep(.02)
        self.assertEqual(int(self.count.read_text()), delivered_before + 4)

        os.killpg(stream.pid, signal.SIGTERM)
        stdout, stderr = stream.communicate(timeout=3)
        self.assertEqual(stream.returncode, -signal.SIGTERM, stderr)
        events = [json.loads(line) for line in (first_line + stdout).splitlines()]
        self.assertEqual(events, [
            {'attention': True, 'source': 'codex'},
            {'attention': True, 'source': 'claude'},
            {'attention': True, 'source': 'chatgpt'},
        ])
        self.assertNotIn('private title', stdout)
        self.assertNotIn('body may mention', stdout)


if __name__ == '__main__':
    unittest.main()
