"""Notification LED lifecycle tests using disposable files, never hardware."""
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/oldbook-notification-led'


class NotificationLedTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), 'notification LED helper is missing')
        self.module = runpy.run_path(str(HELPER))
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-led-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.leds = self.root / 'leds'
        self.leds.mkdir()

    def led(self, name, value='0'):
        node = self.leds / name
        node.mkdir()
        (node / 'brightness').write_text(value + '\n')
        (node / 'max_brightness').write_text('1\n')
        return node / 'brightness'

    def test_count_drives_caps_leds_and_leaves_other_lights_alone(self):
        caps = self.led('input2::capslock')
        num = self.led('input2::numlock', '1')
        lights = self.module['CapsLeds'](self.leds)
        lights.sync(True)
        self.assertEqual(caps.read_text().strip(), '1')
        lights.sync(False)
        self.assertEqual(caps.read_text().strip(), '0')
        self.assertEqual(num.read_text().strip(), '1')

    def test_hotplug_and_external_reset_recover_without_a_new_notification(self):
        caps = self.led('input2::capslock')
        lights = self.module['CapsLeds'](self.leds)
        lights.sync(True)
        caps.write_text('0\n')
        hotplug = self.led('input18::capslock')
        lights.sync(True)
        self.assertEqual(caps.read_text().strip(), '1')
        self.assertEqual(hotplug.read_text().strip(), '1')

    def test_invalid_events_cannot_enable_the_light(self):
        parse = self.module['notification_pending']
        self.assertTrue(parse('{"count":2,"dnd":true,"visible":false,"inhibited":false}'))
        self.assertFalse(parse('{"count":0,"dnd":false,"visible":false,"inhibited":false}'))
        for event in ['bad json', '[]', '{}', '{"count":true}', '{"count":"2"}', '{"count":-1}']:
            with self.subTest(event=event), self.assertRaises(ValueError):
                parse(event)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail('LED service did not reach expected state')

    def test_singleton_subscription_restart_and_session_exit_clear_led(self):
        self.check_lifecycle(terminate=False)

    def test_sigterm_clears_led_and_stops_subscription(self):
        self.check_lifecycle(terminate=True)

    def check_lifecycle(self, terminate):
        caps = self.led('input2::capslock')
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        session = self.root / 'session'
        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        server.bind(str(session))
        server.listen()
        server.settimeout(5)
        events = self.root / 'events'
        os.mkfifo(events)
        subscriber = self.root / 'subscriber.py'
        subscriber.write_text(
            'import sys\n'
            f'with open({str(self.root / "starts")!r}, "a") as starts: starts.write("start\\n")\n'
            'with open(sys.argv[1]) as events:\n'
            '    for line in events:\n'
            '        print(line, end="", flush=True)\n')
        command = [sys.executable, str(subscriber), str(events)]
        code = (f'import runpy; from pathlib import Path; '
                f'runpy.run_path({str(HELPER)!r})["run"]('
                f'Path({str(runtime)!r}), Path({str(self.leds)!r}), '
                f'{command!r}, Path({str(session)!r}))')
        args = [sys.executable, '-c', code]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            connection, _ = server.accept()
            self.addCleanup(connection.close)
            # RDWR keeps the fixture itself from blocking if the service fails.
            with os.fdopen(os.open(events, os.O_RDWR), 'w', buffering=1) as stream:
                stream.write(json.dumps({'count': 1}) + '\n')
                self.wait_for(lambda: caps.read_text().strip() == '1')
                duplicate = subprocess.run(args, capture_output=True, text=True, timeout=3)
                self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
                self.assertEqual(caps.read_text().strip(), '1', 'duplicate must not clear active LED')
                stream.write(json.dumps({'count': 0}) + '\n')
                self.wait_for(lambda: caps.read_text().strip() == '0')
            # EOF forces a reconnect; the next subscriber must accept new events.
            self.wait_for(lambda: len((self.root / 'starts').read_text().splitlines()) == 2)
            self.assertEqual(caps.read_text().strip(), '0')
            with os.fdopen(os.open(events, os.O_RDWR), 'w', buffering=1) as stream:
                stream.write(json.dumps({'count': 3}) + '\n')
                self.wait_for(lambda: caps.read_text().strip() == '1')
                if terminate:
                    proc.terminate()
                else:
                    # A crashed compositor can leave its socket path behind.
                    connection.close()
                proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(caps.read_text().strip(), '0')
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
