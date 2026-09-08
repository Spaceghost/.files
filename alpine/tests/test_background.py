"""Crossfade wallpaper daemon: geometry, easing, protocol and gallery integration."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / 'alpine/desktop/.local/lib/oldbook'
import sys  # noqa: E402
sys.path.insert(0, str(LIB))
import background_fade as fade  # noqa: E402


class Geometry(unittest.TestCase):
    def test_fill_covers_target_and_keeps_aspect(self):
        width, height, x, y = fade.fill_geometry(1586, 992, 2880, 1800)
        self.assertGreaterEqual(width, 2880)
        self.assertGreaterEqual(height, 1800)
        self.assertAlmostEqual(width / height, 1586 / 992, places=2)
        self.assertLessEqual(x, 0)
        self.assertLessEqual(y, 0)
        # The overflow is split evenly, so the crop stays centred.
        self.assertEqual(x, (2880 - width) // 2)
        self.assertEqual(y, (1800 - height) // 2)

    def test_fill_of_exact_aspect_is_exact(self):
        self.assertEqual(fade.fill_geometry(1600, 900, 1280, 720), (1280, 720, 0, 0))

    def test_fill_rejects_empty_sizes(self):
        with self.assertRaises(ValueError):
            fade.fill_geometry(0, 10, 100, 100)

    def test_progress_is_monotonic_and_settles_exactly(self):
        values = [fade.progress(t, 1000) for t in range(0, 1101, 50)]
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[-1], 1.0)
        self.assertEqual(fade.progress(1000, 1000), 1.0)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in values))
        self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))
        self.assertEqual(fade.progress(0, 0), 1.0)
        self.assertEqual(fade.progress(-5, 1000), 0.0)

    def test_ease_out_never_overshoots(self):
        self.assertEqual(fade.ease_out(2.0), 1.0)
        self.assertEqual(fade.ease_out(-1.0), 0.0)
        self.assertGreater(fade.ease_out(0.25), 0.25)

    def test_reveal_reaches_the_far_corner(self):
        radius = fade.reveal_radius((100, 100), 1440, 900)
        self.assertAlmostEqual(radius, ((1440 - 100) ** 2 + (900 - 100) ** 2) ** .5)
        inner, outer = fade.reveal_rings(1.0, radius)
        self.assertGreaterEqual(inner, radius)
        self.assertGreater(outer, inner)
        self.assertEqual(fade.reveal_rings(0.0, radius), (0.0, 0.0))


class Protocol(unittest.TestCase):
    def test_set_round_trip_and_clamping(self):
        message = fade.parse_request(fade.encode_request(
            'set', path='/tmp/x.png', duration_ms=99999, origin=(3, 4)))
        self.assertEqual(message['path'], '/tmp/x.png')
        self.assertEqual(message['duration_ms'], fade.MAX_DURATION_MS)
        self.assertEqual(message['origin'], (3.0, 4.0))
        self.assertEqual(fade.parse_request(fade.encode_request('status'))['action'], 'status')

    def test_invalid_requests_are_rejected(self):
        for payload in [b'{', b'[]', b'{"action": "explode", "id": "1"}',
                        b'{"action": "set", "id": "1", "path": "relative.png"}',
                        b'{"action": "set", "id": "1", "path": "/a.png", "duration_ms": "fast"}',
                        b'{"action": "set", "id": "1", "path": "/a.png", "origin": [1]}',
                        b'{"action": "set", "id": "1", "path": "/a.png", "origin": [1, "y"]}',
                        b'{"action": "set", "id": "", "path": "/a.png"}',
                        b'{"action": "set", "id": "' + b'x' * 65 + b'", "path": "/a.png"}',
                        b'x' * (fade.MAX_MESSAGE + 1)]:
            with self.assertRaises(ValueError, msg=payload[:40]):
                fade.parse_request(payload)

    def test_origin_parsing(self):
        self.assertEqual(fade.parse_origin('12.5,7'), (12.5, 7.0))
        for text in ('12', 'a,b', 'nan,1', None):
            with self.assertRaises(ValueError):
                fade.parse_origin(text)

    def test_ipc_frames(self):
        frame = fade.ipc_frame(fade.IPC_SUBSCRIBE, '["output"]')
        length, kind = fade.ipc_unpack(frame[:fade.IPC_HEADER.size])
        self.assertEqual((length, kind), (len('["output"]'), fade.IPC_SUBSCRIBE))
        with self.assertRaises(ValueError):
            fade.ipc_unpack(b'not-i3-ipc-hdr')

    def test_request_reports_no_daemon_accepted_and_settled(self):
        with tempfile.TemporaryDirectory(prefix='background-proto-') as directory:
            env = {'XDG_RUNTIME_DIR': directory, 'SWAYSOCK': directory + '/sway-ipc.1.2.sock'}
            with mock.patch.dict(os.environ, env):
                self.assertIsNone(fade.crossfade('/a.png', ack_timeout=.2, settle_timeout=0))
                fade.runtime_directory().mkdir(mode=0o700, exist_ok=True)
                server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                server.bind(str(fade.endpoint()))
                server.settimeout(5)
                seen = []

                def serve(settle):
                    data, address = server.recvfrom(fade.MAX_MESSAGE)
                    message = fade.parse_request(data)
                    seen.append(message)
                    server.sendto(json.dumps({'ok': True, 'id': message['id'],
                                              'state': 'accepted'}).encode(), address)
                    if settle:
                        server.sendto(json.dumps({'ok': True, 'id': message['id'],
                                                  'state': 'settled'}).encode(), address)

                worker = threading.Thread(target=serve, args=(True,))
                worker.start()
                reply = fade.crossfade('/a.png', duration_ms=5, origin=(1, 1), settle_timeout=2)
                worker.join()
                self.assertEqual(reply['state'], 'settled')
                self.assertEqual(seen[-1]['origin'], (1.0, 1.0))
                worker = threading.Thread(target=serve, args=(False,))
                worker.start()
                reply = fade.crossfade('/b.png', settle_timeout=.2)
                worker.join()
                self.assertEqual(reply['state'], 'accepted')
                server.close()
                self.assertEqual([p.name for p in Path(directory, 'oldbook').iterdir()
                                  if 'reply' in p.name], [])


class Stacking(unittest.TestCase):
    def surfaces(self, *names):
        return {'layer_shell_surfaces': [{'layer': 'background', 'namespace': n} for n in names]
                + [{'layer': 'bottom', 'namespace': 'oldbook-scripture'}]}

    def test_orders_are_listed_top_first(self):
        self.assertEqual(fade.surface_order(self.surfaces('wallpaper')),
                         {'present': False, 'buried': False, 'cards_below': False})
        # Healthy: cards newest (top), our surface next, swaybg underneath.
        self.assertEqual(fade.surface_order(self.surfaces('conky', 'oldbook-background', 'wallpaper')),
                         {'present': True, 'buried': False, 'cards_below': False})
        # A respawned swaybg covers us; a card created before us is hidden.
        self.assertEqual(fade.surface_order(self.surfaces('wallpaper', 'oldbook-background', 'conky')),
                         {'present': True, 'buried': True, 'cards_below': True})
        # During a re-creation both surfaces exist; the newest one counts.
        self.assertEqual(fade.surface_order(self.surfaces('conky', 'oldbook-background', 'wallpaper',
                                                          'oldbook-background')),
                         {'present': True, 'buried': False, 'cards_below': False})

    def test_swaybg_discovery_uses_the_compositor_pid_and_owner(self):
        with tempfile.TemporaryDirectory(prefix='fake-proc-') as directory:
            proc = Path(directory)
            uid = os.getuid()

            def process(pid, ppid, argv):
                entry = proc / str(pid)
                entry.mkdir()
                (entry / 'stat').write_text(f'{pid} ({argv[0]}) S {ppid} 1 1 0 -1 0 0\n')
                (entry / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in argv) + b'\0')
            process(41, 40, ['swaybg', '-o', '*', '-i', '/img/a.png', '-m', 'fill'])
            process(42, 40, ['swaybg', '-o', 'eDP-1', '-i', '/img/b.png', '-m', 'fill',
                             '-o', 'HDMI-A-1', '-i', '/img/c.png', '-m', 'fill'])
            process(43, 99, ['swaybg', '-o', '*', '-i', '/img/other-session.png'])
            process(44, 40, ['python3', '-i', '/img/not-swaybg.png'])
            (proc / 'self').mkdir()
            socket_path = f'/run/user/{uid}/sway-ipc.{uid}.40.sock'
            self.assertEqual(fade.sway_background_images(socket_path, proc=proc),
                             {'*': '/img/a.png', 'eDP-1': '/img/b.png', 'HDMI-A-1': '/img/c.png'})
            self.assertEqual(fade.sway_background_images('/nonsense', proc=proc), {})
            self.assertEqual(fade.sway_background_images(None, proc=proc), {})



if __name__ == '__main__':
    unittest.main()
