"""Lock acquisition regression tests; never connect to the live compositor."""
import json
import os
import runpy
import signal
import socket
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
LOCK = REPO / 'alpine/desktop/.local/bin/oldbook-lock'


class LockRegressionTests(unittest.TestCase):
    def test_indicator_palette_follows_the_selected_theme(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-theme-') as directory:
            themes = Path(directory)
            (themes / 'current').write_text('violet\n')
            (themes / 'violet.json').write_text(json.dumps({'palette': {
                'background': '#13091f', 'surface': '#261631',
                'foreground': '#eaddf5', 'accent': '#dca7ff',
                'muted': '#816b91'}}))
            lock = runpy.run_path(str(LOCK))
            lock['lock_arguments'].__globals__['THEMES'] = themes

            arguments = lock['lock_arguments'](9)

            self.assertEqual(arguments[arguments.index('--inside-color') + 1], '13091fee')
            self.assertEqual(arguments[arguments.index('--ring-color') + 1], 'dca7ffff')
            self.assertEqual(arguments[arguments.index('--text-color') + 1], 'eaddf5ff')
            expected_states = {
                '--bs-hl-color': 'eaddf5ff',
                '--caps-lock-bs-hl-color': '816b91ff',
                '--caps-lock-key-hl-color': 'dca7ffff',
                '--inside-caps-lock-color': '261631ee',
                '--ring-caps-lock-color': 'dca7ffff',
                '--text-clear-color': 'eaddf5ff',
                '--text-caps-lock-color': 'dca7ffff',
                '--line-clear-color': '00000000',
                '--line-caps-lock-color': '00000000',
                '--line-ver-color': '00000000',
                '--line-wrong-color': '00000000',
            }
            for option, expected in expected_states.items():
                with self.subTest(option=option):
                    self.assertIn(option, arguments)
                    self.assertEqual(arguments[arguments.index(option) + 1], expected)

    def test_process_name_alone_never_proves_readiness(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            helper = fake_bin / 'swaylockd'
            helper.write_text('#!/bin/sh\nexit 1\n')
            helper.chmod(0o755)
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory, WAYLAND_DISPLAY='wayland-test',
                       PATH=str(fake_bin) + ':/usr/bin:/bin', OLDBOOK_LOCK_BACKEND='stock')
            fake = subprocess.Popen(['swaylock', '-c', 'import time; time.sleep(20)'],
                                    executable='/usr/bin/python3')
            try:
                time.sleep(0.05)
                result = subprocess.run([str(LOCK)], env=env, capture_output=True,
                                        text=True, timeout=3)
                self.assertNotEqual(result.returncode, 0,
                                    'a matching process has never sent lock readiness')
            finally:
                fake.terminate()
                fake.wait()

    def test_concurrent_calls_wait_for_one_real_readiness_event(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            helper = root / 'swaylockd'
            helper.write_text("#!/usr/bin/python3\nimport os,sys,time\n"
                              f"with open({str(root / 'starts')!r}, 'a') as f: f.write(str(os.getpid())+'\\n')\n"
                              "time.sleep(.3)\n"
                              "os.write(int(sys.argv[sys.argv.index('-R')+1]), b'\\n')\n"
                              "time.sleep(20)\n")
            helper.chmod(0o755)
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory, WAYLAND_DISPLAY='wayland-test',
                       PATH=directory + ':/usr/bin:/bin', OLDBOOK_LOCK_BACKEND='stock')
            clients = []
            try:
                started = time.monotonic()
                clients = [subprocess.Popen([str(LOCK)], env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True) for _ in range(2)]
                for client in clients:
                    output, error = client.communicate(timeout=3)
                    self.assertEqual(client.returncode, 0, error)
                self.assertGreaterEqual(time.monotonic() - started, .3)
                self.assertEqual(len((root / 'starts').read_text().splitlines()), 1)
                ready = json.loads((root / 'oldbook-screen-lock/ready.json').read_text())
                # A fresh call reuses the proven, live process without another launch.
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len((root / 'starts').read_text().splitlines()), 1)
                # A stale identity must never be accepted as proof of a current lock.
                original = json.loads(json.dumps(ready))
                ready['process']['start_time'] = 'invalid'
                (root / 'oldbook-screen-lock/ready.json').write_text(json.dumps(ready))
                helper.write_text('#!/bin/sh\nexit 1\n')
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=2)
                self.assertNotEqual(result.returncode, 0)
                # The still-live supervisor cannot authorize a different compositor.
                (root / 'oldbook-screen-lock/ready.json').write_text(json.dumps(original))
                wayland.close()
                (root / 'wayland-test').unlink()
                replacement = socket.socket(socket.AF_UNIX)
                self.addCleanup(replacement.close)
                replacement.bind(str(root / 'wayland-test'))
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=2)
                self.assertNotEqual(result.returncode, 0)
            finally:
                for client in clients:
                    if client.poll() is None:
                        client.kill()
                        client.wait()
                if (root / 'starts').exists():
                    for pid in (root / 'starts').read_text().splitlines():
                        try:
                            os.killpg(int(pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_unready_helper_is_killed_and_never_records_success(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            helper = root / 'swaylockd'
            helper.write_text("#!/usr/bin/python3\nimport os,time\n"
                              f"open({str(root / 'started')!r}, 'w').write(str(os.getpid()))\n"
                              "time.sleep(20)\n")
            helper.chmod(0o755)
            code = ("import runpy; from pathlib import Path; "
                    f"m=runpy.run_path({str(LOCK)!r}); "
                    f"m['acquire_lock'](Path({directory!r}), {str(helper)!r}, timeout=.2)")
            result = subprocess.run(['/usr/bin/python3', '-c', code], env=dict(os.environ, WAYLAND_DISPLAY='wayland-test'), capture_output=True, text=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('did not report readiness', result.stderr)
            self.assertFalse((root / 'oldbook-screen-lock/ready.json').exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(int((root / 'started').read_text()), 0)

    def test_nonprivate_runtime_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-test-') as directory:
            Path(directory).chmod(0o755)
            result = subprocess.run([str(LOCK)], env=dict(os.environ, XDG_RUNTIME_DIR=directory),
                                    capture_output=True, text=True, timeout=2)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('owned private directory', result.stderr)


def fake_home(root, painting=True):
    """A HOME with a tiny painting, its story, and no reading history."""
    home = root / 'home'
    (home / '.local/share/oldbook').mkdir(parents=True)
    (home / '.local/state/oldbook/wallpaper').mkdir(parents=True)
    if painting:
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 96, 60)
        pixbuf.fill(0x3c6a8aff)
        pixbuf.savev(str(home / '.local/share/oldbook/current-wallpaper.png'), 'png', [], [])
        (home / '.local/state/oldbook/wallpaper/state.json').write_text(json.dumps({
            'file': 'alpine/assets/gallery/current-wallpaper.png',
            'title': 'Zorak Learns Fossil', 'description': 'A tense tutorial. Nobody commits.'}))
    return home


def fake_themes(root):
    themes = root / 'themes'
    themes.mkdir()
    (themes / 'current').write_text('gruvbox-dark\n')
    (themes / 'gruvbox-dark.json').write_text(json.dumps({'palette': {
        'background': '#282828', 'background_hard': '#1d2021', 'surface': '#3c3836', 'border': '#504945',
        'foreground': '#ebdbb2', 'muted': '#928374', 'yellow': '#fabd2f'}}))
    return themes


class LockSceneTests(unittest.TestCase):
    """The swaylock-effects scene: composed painting, caption, idle-invisible ring."""

    def scene(self, root, painting=True):
        import runpy
        home = fake_home(root, painting)
        cache = root / 'cache'
        cache.mkdir(mode=0o700)
        runtime = root / 'runtime'
        runtime.mkdir(mode=0o700)
        environment = {'HOME': str(home), 'XDG_DATA_HOME': str(home / '.local/share'),
                       'XDG_STATE_HOME': str(home / '.local/state'), 'OLDBOOK_LOCK_CACHE': str(cache)}
        saved = {key: os.environ.get(key) for key in environment}
        os.environ.update(environment)
        try:
            module = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py'))
            palette = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/overlay_theme.py'))['read_palette'](fake_themes(root))
            arguments = module['scene_arguments'](5, palette, (1440, 900, 1), runtime, home=home)
            again = module['scene_arguments'](5, palette, (1440, 900, 1), runtime, home=home)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        return arguments, again, cache, runtime

    def test_scene_composes_the_painting_and_caption_with_an_idle_invisible_ring(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-scene-') as directory:
            arguments, again, cache, runtime = self.scene(Path(directory))
            self.assertEqual(arguments[:2], ['-R', '5'])
            self.assertIn('--screenshots', arguments)
            self.assertIn('--fade-in', arguments)
            self.assertNotIn('--grace', arguments)
            composes = [arguments[index + 1] for index, item in enumerate(arguments) if item == '--effect-compose']
            self.assertEqual(len(composes), 2)
            self.assertTrue(composes[0].startswith('0,0;100%x100%;northwest;'))
            scene = Path(composes[0].split(';')[-1])
            self.assertEqual(scene.parent, cache)
            self.assertTrue(scene.is_file())
            self.assertTrue(composes[1].startswith('44,-44;560x-1;southwest;'))
            caption = Path(composes[1].split(';')[-1])
            self.assertEqual(caption.parent, runtime / 'oldbook-screen-lock')
            self.assertTrue(caption.is_file())
            self.assertEqual(oct(caption.stat().st_mode & 0o777), '0o600')
            for option, expected in {'--ring-idle-color': '00000000', '--inside-idle-color': '00000000',
                                     '--text-idle-color': 'ebdbb2ff', '--ring-color': 'fabd2fff',
                                     '--key-hl-color': 'fabd2fff', '--ring-ver-color': '928374ff',
                                     '--inside-color': '1d2021b8', '--timestr': '%H:%M'}.items():
                with self.subTest(option=option):
                    self.assertEqual(arguments[arguments.index(option) + 1], expected)
            self.assertIn('--clock', arguments)
            self.assertIn('--indicator', arguments)
            self.assertEqual(arguments[arguments.index('--indicator-x-position') + 1], '720')
            # The cached scene and caption are reused rather than rendered again.
            self.assertEqual(again, arguments)
            self.assertEqual(sorted(path.name for path in cache.glob('*.png')), [scene.name])

    def test_scene_without_a_painting_degrades_to_the_palette_background(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-scene-') as directory:
            arguments, _, cache, _ = self.scene(Path(directory), painting=False)
            self.assertEqual(arguments[arguments.index('-c') + 1], '282828')
            composes = [arguments[index + 1] for index, item in enumerate(arguments) if item == '--effect-compose']
            self.assertEqual(len(composes), 1, 'only the caption card is composed')
            self.assertEqual(list(cache.glob('*.png')), [])


class LockBackendTests(unittest.TestCase):
    def test_failed_effects_locker_falls_back_to_the_stock_locker(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-fallback-') as directory:
            root = Path(directory)
            home = fake_home(root, painting=False)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            (fake_bin / 'swaylock-effects').write_text('#!/bin/sh\necho effects >> ' + str(root / 'launches') + '\nexit 1\n')
            (fake_bin / 'swaylockd').write_text("#!/usr/bin/python3\nimport os,sys,time\n"
                                                f"open({str(root / 'launches')!r}, 'a').write('stock\\n')\n"
                                                "os.write(int(sys.argv[sys.argv.index('-R')+1]), b'\\n')\n"
                                                "time.sleep(20)\n")
            for helper in fake_bin.iterdir():
                helper.chmod(0o755)
            env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / '.local/share'),
                       XDG_STATE_HOME=str(home / '.local/state'), XDG_RUNTIME_DIR=directory,
                       WAYLAND_DISPLAY='wayland-test', PATH=str(fake_bin) + ':/usr/bin:/bin',
                       OLDBOOK_LOCK_BACKEND='effects', OLDBOOK_LOCK_CACHE=str(root / 'cache'))
            env.pop('SWAYSOCK', None)
            try:
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('swaylock-effects failed', result.stderr)
                self.assertEqual((root / 'launches').read_text().split(), ['effects', 'stock'])
                record = json.loads((root / 'oldbook-screen-lock/ready.json').read_text())
                self.assertEqual(record['locker'], 'swaylockd')
            finally:
                try:
                    record = json.loads((root / 'oldbook-screen-lock/ready.json').read_text())
                    os.killpg(record['process']['pid'], signal.SIGKILL)
                except (OSError, ValueError, KeyError):
                    pass

    def test_supervisor_restarts_a_crashed_locker_without_the_first_run_options(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-supervise-') as directory:
            root = Path(directory)
            locker = root / 'locker.py'
            locker.write_text("import os, sys, json, signal\n"
                              f"runs = {str(root / 'runs')!r}\n"
                              "count = len(open(runs).read().splitlines()) if os.path.exists(runs) else 0\n"
                              "open(runs, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                              "if '-R' in sys.argv:\n"
                              "    os.write(int(sys.argv[sys.argv.index('-R') + 1]), b'\\n')\n"
                              "if count == 0:\n"
                              "    os.kill(os.getpid(), signal.SIGSEGV)\n"
                              "sys.exit(0)\n")
            read_fd, write_fd = os.pipe()
            env = dict(os.environ, XDG_STATE_HOME=str(root / 'state'))
            process = subprocess.Popen([str(LOCK), 'supervise', '--', '/usr/bin/python3', str(locker),
                                        '-R', str(write_fd), '--fade-in', '0.4', '--screenshots',
                                        '--clock', '--effect-compose', 'x'],
                                       pass_fds=(write_fd,), env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
            os.close(write_fd)
            self.assertEqual(os.read(read_fd, 1), b'\n', 'readiness arrives from the first run')
            self.assertEqual(os.read(read_fd, 1), b'', 'the pipe closes once the first locker owns it')
            os.close(read_fd)
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            runs = [json.loads(line) for line in (root / 'runs').read_text().splitlines()]
            self.assertEqual(len(runs), 2)
            self.assertIn('-R', runs[0])
            self.assertEqual(runs[1], ['--clock', '--effect-compose', 'x'])
            self.assertIn('terminated by signal 11', (root / 'state/oldbook/lock.log').read_text())

    def test_first_run_options_are_stripped_only_once(self):
        lock = runpy.run_path(str(LOCK))
        stripped = lock['strip_first_run_options'](['swaylock-effects', '-R', '7', '--fade-in', '0.4', '-S',
                                                    '--screenshots', '--clock', '--ready-fd', '9', '-c', '282828'])
        self.assertEqual(stripped, ['swaylock-effects', '--clock', '-c', '282828'])


if __name__ == '__main__':
    unittest.main()
