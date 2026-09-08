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

HELPER = Path(__file__).resolve().parents[1] / 'desktop/.local/bin/mbp-intel-notification-led'


class NotificationLedTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(HELPER.is_file(), 'notification LED helper is missing')
        self.module = runpy.run_path(str(HELPER))
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-led-test-')
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

    def test_caps_led_control_leaves_other_lights_alone(self):
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

    def test_only_attributed_ai_attention_events_start_flashing(self):
        self.assertIn('attention_event', self.module)
        parse = self.module['attention_event']
        for source in ('codex', 'claude', 'chatgpt'):
            self.assertEqual(parse(json.dumps({'attention': True, 'source': source})),
                             source)
        for event in [[], {}, {'count': 9}, {'attention': 'true', 'source': 'codex'},
                      {'attention': True, 'source': 'firefox'}, {'attention': True}]:
            self.assertIsNone(parse(json.dumps(event)))
        with self.assertRaises(ValueError):
            parse('not json')

    def test_attention_keeps_flashing_until_no_window_is_pending(self):
        self.assertIn('AttentionFlash', self.module)
        flash = self.module['AttentionFlash']()
        self.assertFalse(flash.enabled(100))
        flash.reconcile(True, 100)
        for now, expected in [(100, True), (100.6, False), (101.1, True),
                              (104.6, False), (105.1, True), (120.1, True)]:
            self.assertEqual(flash.enabled(now), expected, f'at {now}')
        flash.reconcile(False, 121)
        self.assertFalse(flash.enabled(121))

    def test_new_alert_does_not_reset_the_existing_flash_phase(self):
        self.assertIn('AttentionFlash', self.module)
        flash = self.module['AttentionFlash']()
        flash.reconcile(True, 100)
        flash.reconcile(True, 100.4)
        self.assertFalse(flash.enabled(100.6))
        self.assertTrue(flash.enabled(105.1))

    def test_exact_windows_clear_individually_on_focus_or_close(self):
        pending = self.module['PendingWindows']()
        applications = {
            10: {'kind': 'codex', 'tty': '/dev/pts/2', 'focused': False},
            11: {'kind': 'codex', 'tty': '/dev/pts/3', 'focused': False},
        }
        pending.add('codex', applications, {'tty': '/dev/pts/2', 'tmux_pane': None})
        pending.add('codex', applications, {'tty': '/dev/pts/3', 'tmux_pane': None})
        self.assertEqual(pending.windows, {10: 'codex', 11: 'codex'})

        applications[10]['focused'] = True
        pending.reconcile(applications)
        self.assertEqual(pending.windows, {11: 'codex'})
        self.assertTrue(pending.pending)

        pending.reconcile({10: applications[10]})
        self.assertFalse(pending.pending)

    def test_unrouted_alert_queues_every_candidate_until_each_is_visited(self):
        pending = self.module['PendingWindows']()
        applications = {
            20: {'kind': 'claude', 'focused': False},
            21: {'kind': 'claude', 'focused': False},
        }
        pending.add('claude', applications)
        self.assertEqual(pending.windows, {20: 'claude', 21: 'claude'})

        applications[20]['focused'] = True
        pending.reconcile(applications)
        self.assertEqual(pending.windows, {21: 'claude'})
        self.assertTrue(pending.pending)

        applications[20]['focused'] = False
        applications[21]['focused'] = True
        pending.reconcile(applications)
        self.assertFalse(pending.pending)

    def test_no_candidate_fallback_clears_on_provider_focus_or_control_center(self):
        pending = self.module['PendingWindows']()
        pending.add('chatgpt', {})
        self.assertIn('chatgpt', pending.fallback)

        pending.reconcile({21: {'kind': 'chatgpt', 'focused': True}})
        self.assertFalse(pending.pending)

        pending.add('chatgpt', {})
        self.assertTrue(pending.pending)

        pending.acknowledge_fallback()
        self.assertFalse(pending.pending)

    def test_focused_target_is_already_seen_and_never_becomes_pending(self):
        pending = self.module['PendingWindows']()
        applications = {
            10: {'kind': 'codex', 'tty': '/dev/pts/2', 'focused': True},
        }
        pending.add('codex', applications, {'tty': '/dev/pts/2', 'tmux_pane': None})
        self.assertFalse(pending.pending)

    def test_recent_owned_codex_record_supplies_exact_route(self):
        runtime = self.root / 'runtime-record'
        events = runtime / 'mbp-intel/codex-events'
        events.mkdir(parents=True)
        now = int(time.time())
        (events / 'event.json').write_text(json.dumps({
            'version': 1,
            'event': 'turn-complete',
            'observed_at': now,
            'valid_until': now + 300,
            'tmux_pane': '%7',
            'tty': '/dev/pts/4',
        }))
        self.assertEqual(self.module['latest_codex_route'](runtime, now), {
            'tmux_pane': '%7', 'tty': '/dev/pts/4'})

    def test_codex_route_ignores_malformed_types_and_handles_equal_ties(self):
        runtime = self.root / 'runtime-record-tie'
        events = runtime / 'mbp-intel/codex-events'
        events.mkdir(parents=True)
        now = int(time.time())
        base = {
            'version': 1,
            'event': 'turn-complete',
            'observed_at': now,
            'valid_until': now + 300,
            'tmux_pane': None,
        }
        (events / 'bad.json').write_text(json.dumps({**base, 'tty': 4}))
        for name, tty in (('first.json', '/dev/pts/8'),
                          ('second.json', '/dev/pts/9')):
            path = events / name
            path.write_text(json.dumps({**base, 'tty': tty}))
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        route = self.module['latest_codex_route'](runtime, now)
        self.assertIn(route, ({'tty': '/dev/pts/8', 'tmux_pane': None},
                              {'tty': '/dev/pts/9', 'tmux_pane': None}))

    def test_notification_center_visibility_only_acknowledges_fallback(self):
        parse = self.module['control_center_state']
        self.assertIs(parse('{"visible":true,"count":9}'), True)
        self.assertIs(parse('{"visible":false,"count":9}'), False)
        self.assertIsNone(parse('{"count":9}'))

    def test_only_window_lifecycle_and_focus_events_trigger_snapshots(self):
        relevant = self.module['relevant_window_event']
        for change in ('focus', 'close', 'new'):
            self.assertTrue(relevant({'change': change}))
        for change in ('title', 'move', 'floating', 'fullscreen_mode'):
            self.assertFalse(relevant({'change': change}))
        self.assertFalse(relevant([]))

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

    def test_control_subscriber_eof_cannot_silently_acknowledge_a_later_alert(self):
        caps = self.led('input2::capslock')
        runtime = self.root / 'runtime-control'
        runtime.mkdir(mode=0o700)
        session_path = self.root / 'session-control'
        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        server.bind(str(session_path))
        server.listen()
        server.settimeout(5)
        attention = self.root / 'attention-events'
        control = self.root / 'control-events'
        os.mkfifo(attention)
        os.mkfifo(control)
        subscriber = self.root / 'control-subscriber.py'
        subscriber.write_text(
            'import sys\n'
            'with open(sys.argv[2], "a") as starts: starts.write("start\\n")\n'
            'with open(sys.argv[1]) as events:\n'
            '    for line in events:\n'
            '        print(line, end="", flush=True)\n')
        starts = self.root / 'control-starts'
        attention_command = [sys.executable, str(subscriber), str(attention),
                             str(self.root / 'attention-starts')]
        control_command = [sys.executable, str(subscriber), str(control), str(starts)]
        code = (f'import runpy; from pathlib import Path; '
                f'runpy.run_path({str(HELPER)!r})["run"]('
                f'Path({str(runtime)!r}), Path({str(self.leds)!r}), '
                f'{attention_command!r}, Path({str(session_path)!r}), '
                f'control_command={control_command!r})')
        proc = subprocess.Popen(
            [sys.executable, '-c', code], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        try:
            connection, _ = server.accept()
            self.addCleanup(connection.close)
            with os.fdopen(os.open(attention, os.O_RDWR), 'w', buffering=1) as alerts:
                with open(control, 'w', buffering=1) as center:
                    center.write('{"visible":true}\n')
                self.wait_for(lambda: starts.is_file()
                              and len(starts.read_text().splitlines()) >= 2)
                alerts.write('{"attention":true,"source":"chatgpt"}\n')
                self.wait_for(lambda: caps.read_text().strip() == '1')
        finally:
            proc.terminate()
            proc.communicate(timeout=5)
        self.assertEqual(caps.read_text().strip(), '0')

    def check_lifecycle(self, terminate):
        caps = self.led('input2::capslock', '1')
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
                stream.write(json.dumps({'count': 5}) + '\n')
                self.wait_for(lambda: caps.read_text().strip() == '0')
                stream.write(json.dumps({'attention': True, 'source': 'codex'}) + '\n')
                self.wait_for(lambda: caps.read_text().strip() == '1')
                duplicate = subprocess.run(args, capture_output=True, text=True, timeout=3)
                self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
                self.assertEqual(int((runtime / 'mbp-intel-notification-led.lock').read_text()), proc.pid)
                # The off phase happens while notifications remain unread.
                self.wait_for(lambda: caps.read_text().strip() == '0')
            # EOF forces a reconnect; the next subscriber must accept new events.
            self.wait_for(lambda: len((self.root / 'starts').read_text().splitlines()) == 2)
            self.assertEqual(caps.read_text().strip(), '0')
            with os.fdopen(os.open(events, os.O_RDWR), 'w', buffering=1) as stream:
                stream.write(json.dumps({'attention': True, 'source': 'claude'}) + '\n')
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
