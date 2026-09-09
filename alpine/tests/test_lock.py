"""Lock acquisition regression tests; never connect to the live compositor."""
import hashlib
import json
import os
import re
import runpy
import signal
import socket
from pathlib import Path
import shutil
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

    def test_the_locker_holds_a_power_key_inhibitor_for_its_whole_life(self):
        """A short press of the MacBook's power key, which sits beside
        Backspace, powers the machine off: brushing it while typing a password
        must not end the session instead of unlocking it. Alpine supplies the
        inhibitor as elogind's and the Bazzite replay as systemd's."""
        for inhibitor in ('elogind-inhibit', 'systemd-inhibit'):
            with self.subTest(inhibitor=inhibitor):
                self.assert_the_locker_holds(inhibitor)

    def assert_the_locker_holds(self, inhibitor):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-power-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            inhibit = fake_bin / inhibitor
            inhibit.write_text('#!/bin/sh\n'
                               f'printf "%s\\n" "$@" > {root / "inhibit-arguments"}\n'
                               'while [ "$1" != "--" ]; do shift; done\n'
                               'shift\n'
                               f'echo $$ > {root / "holder-pid"}\n'
                               'exec "$@"\n')
            inhibit.chmod(0o755)
            helper = fake_bin / 'swaylockd'
            helper.write_text('#!/usr/bin/python3\nimport os,sys,time\n'
                              f'open({str(root / "locker-pid")!r}, "w").write(str(os.getpid()))\n'
                              'os.write(int(sys.argv[sys.argv.index("-R") + 1]), b"\\n")\n'
                              'time.sleep(20)\n')
            helper.chmod(0o755)
            for command in ('python3', 'cat'):
                (fake_bin / command).symlink_to(shutil.which(command))
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory,
                       WAYLAND_DISPLAY='wayland-test', OLDBOOK_LOCK_BACKEND='stock',
                       PATH=str(fake_bin))
            result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = (root / 'inhibit-arguments').read_text().splitlines()
            self.assertIn('--what=handle-power-key', arguments)
            self.assertIn('--mode=block', arguments)
            holder = int((root / 'holder-pid').read_text())
            locker = int((root / 'locker-pid').read_text())
            os.kill(holder, 0)  # The lock is up and elogind is still held off the key.
            os.killpg(locker, signal.SIGKILL)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(holder, 0)
                except ProcessLookupError:
                    break
                time.sleep(.05)
            else:
                self.fail('the power key stayed inhibited after the lock ended')

    def test_a_missing_inhibitor_never_prevents_locking(self):
        """A power key that still works is no reason to leave the session open."""
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-nopower-') as directory:
            root = Path(directory)
            wayland = socket.socket(socket.AF_UNIX)
            wayland.bind(str(root / 'wayland-test'))
            self.addCleanup(wayland.close)
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            helper = fake_bin / 'swaylockd'
            helper.write_text('#!/usr/bin/python3\nimport os,sys,time\n'
                              f'open({str(root / "locker-pid")!r}, "w").write(str(os.getpid()))\n'
                              'os.write(int(sys.argv[sys.argv.index("-R") + 1]), b"\\n")\n'
                              'time.sleep(20)\n')
            helper.chmod(0o755)
            (fake_bin / 'python3').symlink_to(shutil.which('python3'))
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory,
                       WAYLAND_DISPLAY='wayland-test', OLDBOOK_LOCK_BACKEND='stock',
                       PATH=str(fake_bin))
            try:
                result = subprocess.run([str(LOCK)], env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                if (root / 'locker-pid').exists():
                    try:
                        os.killpg(int((root / 'locker-pid').read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

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

    def test_the_blur_is_a_named_documented_value_and_softer_than_it_was(self):
        """The user asked for less blur on the lock images. The strength used to
        be `max(6, round(work_w / 110))` inline in the middle of the render; it
        is now a named constant with a tuning table beside it, so the next
        adjustment is an edit rather than an excavation."""
        module = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py'))
        source = (REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py').read_text()
        self.assertIn('_box_blur(image, blur_radius(work_w)', source)
        self.assertNotIn('_box_blur(image, max(', source, 'the magic number left the render')
        self.assertIn('#      190', source, 'the tuning table stays beside the constant')
        self.assertEqual(module['BLUR_WIDTH_DIVISOR'], 190)
        # A 2880-wide panel renders the scene at 1440; that used to blur by 13.
        self.assertEqual(module['blur_radius'](1440), 8)
        self.assertLess(module['blur_radius'](1440), 13, 'the painting is clearer than before')
        self.assertEqual(module['blur_radius'](320), module['BLUR_MINIMUM_RADIUS'],
                         'a tiny output still gets a floor, never a sharp painting')
        self.assertGreaterEqual(module['SCENE_VERSION'], 2,
                                'a changed blur must not be served from the old cache')

    def test_the_dissolve_is_kept_and_the_measurement_that_says_so_is_recorded(self):
        """--fade-in looks like the cause of the blank moment at lock time and
        measurably is not: 70 ms with it against 94-103 ms without. Deleting it
        to chase the flash would make the flash worse and lose the dissolve
        LOCK-THEME pins, so the numbers live next to the argument."""
        source = (REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py').read_text()
        self.assertIn("'--fade-in', '0.4'", source)
        self.assertIn('ext_session_lock_manager_v1.lock()', source)
        self.assertIn('70 ms', source)

    def test_a_new_painting_warms_the_lock_scene_cache(self):
        """Nothing used to call `oldbook-lock prerender`, so the first lock
        after every gallery rotation rendered the scene inside the lock call:
        2.4-3.7 s of a pressed Super+Escape doing nothing before the locker
        even started, against 0.34-0.37 s warm."""
        source = (REPO / 'alpine/desktop/.local/bin/oldbook-wallpaper').read_text()
        applied = source.split('def apply(', 1)[1].split('\ndef ', 1)[0]
        self.assertIn('warm_lock_scene()', applied)
        warming = source.split('def warm_lock_scene(', 1)[1].split('\ndef ', 1)[0]
        self.assertIn("'prerender'", warming)
        self.assertIn('oldbook-lock', warming)
        self.assertIn('start_new_session=True', warming,
                      'a slow blur must never hold up the fade already on screen')
        self.assertIn('except OSError', warming, 'warming is best effort, never load bearing')

    def test_prerender_writes_the_cache_the_scene_then_reuses(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-warm-') as directory:
            root = Path(directory)
            home = fake_home(root)
            cache = root / 'cache'
            cache.mkdir(mode=0o700)
            env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / '.local/share'),
                       XDG_STATE_HOME=str(home / '.local/state'), XDG_RUNTIME_DIR=str(root),
                       OLDBOOK_LOCK_CACHE=str(cache))
            env.pop('SWAYSOCK', None)
            env.pop('WAYLAND_DISPLAY', None)
            result = subprocess.run([str(LOCK), 'prerender'], env=env, capture_output=True,
                                    text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = sorted(cache.glob('*.png'))
            self.assertEqual(len(rendered), 1)
            module = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py'))
            self.assertTrue(rendered[0].name.endswith(f'-v{module["SCENE_VERSION"]}.png'),
                            f'the cache name must carry the scene version: {rendered[0].name}')
            self.assertEqual(Path(result.stdout.strip()), rendered[0])

    def test_scene_without_a_painting_degrades_to_the_palette_background(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-scene-') as directory:
            arguments, _, cache, _ = self.scene(Path(directory), painting=False)
            self.assertEqual(arguments[arguments.index('-c') + 1], '282828')
            composes = [arguments[index + 1] for index, item in enumerate(arguments) if item == '--effect-compose']
            self.assertEqual(len(composes), 1, 'only the caption card is composed')
            self.assertEqual(list(cache.glob('*.png')), [])


class IndicatorPanelTests(unittest.TestCase):
    """The third swaylock-effects patch, and what it is allowed to be.

    Under ext-session-lock-v1 a locker that dies without unlock_and_destroy
    does not fail open: the compositor stays locked and shows no password
    prompt at all until a replacement takes the lock. Failing stuck is safe and
    unusable, so the bar for adding anything to this binary is that it cannot
    crash it. These tests hold the patch to that.
    """

    PACKAGE = REPO / 'alpine/packages/swaylock-effects'
    PATCH = PACKAGE / '0003-indicator-panel.patch'
    # The lock's trusted path. The drawing hook has no business anywhere near
    # the password, the PAM conversation, the seat or the readiness pipe.
    UNTOUCHABLE = ('pam.c', 'password.c', 'password-buffer.c', 'comm.c',
                   'shadow.c', 'seat.c', 'pam/swaylock')

    def touched(self):
        return sorted({line[6:].strip() for line in self.PATCH.read_text().splitlines()
                       if line.startswith('+++ b/')})

    def test_the_patch_is_pinned_in_the_recipe_by_both_checksums(self):
        raw = self.PATCH.read_bytes()
        recipe = (self.PACKAGE / 'APKBUILD').read_text()
        self.assertIn('\t0003-indicator-panel.patch\n', recipe)
        self.assertIn(f'{hashlib.sha512(raw).hexdigest()}  0003-indicator-panel.patch',
                      recipe)
        manifest = json.loads((self.PACKAGE / 'manifest.json').read_text())
        self.assertIn('0003-indicator-panel.patch', manifest['patches'])
        self.assertEqual(manifest['patches_sha256']['0003-indicator-panel.patch'],
                         hashlib.sha256(raw).hexdigest())
        self.assertGreater(int(re.search(r'^pkgrel=(\d+)$', recipe, re.M).group(1)), 0,
                           'a changed package needs a new release number')

    def test_the_patch_stays_out_of_the_password_and_pam_path(self):
        for name in self.touched():
            self.assertNotIn(Path(name).name, self.UNTOUCHABLE, name)
        self.assertEqual(self.touched(),
                         ['include/panel.h', 'include/swaylock.h', 'main.c',
                          'meson.build', 'panel.c', 'render.c', 'swaylock.1.scd'])

    def test_the_drawing_hook_takes_data_and_never_code(self):
        """A dlopen'd renderer is one segfault from a session with no prompt,
        and a segfault cannot be caught. So the hook is a PNG and a short list
        of clamped numbers: however wrong they are, the worst outcome is that
        nothing is drawn and the locker shows its own indicator."""
        patch = self.PATCH.read_text()
        for forbidden in ('dlopen(', 'dlsym(', 'system(', 'popen(', 'execv', 'fork('):
            self.assertNotIn(forbidden, patch, forbidden)
        # Every refusal that keeps a bad panel out of cairo.
        for guard in ('O_NOFOLLOW', 'S_ISREG', 'st_uid != getuid()',
                      'S_IWGRP | S_IWOTH', 'PANEL_FILE_MAX', 'PANEL_IMAGE_BYTES_MAX',
                      'PANEL_IMAGE_PIXELS_MAX', 'panel_clamp', 'panel_name_is_safe'):
            self.assertIn(guard, patch, guard)
        # cairo's own PNG reader rather than the format-sniffing pixbuf stack.
        self.assertIn('cairo_image_surface_create_from_png', patch)
        self.assertNotIn('gdk_pixbuf_new_from_file', patch)

    def test_a_panel_that_stops_being_written_takes_itself_off_the_screen(self):
        patch = self.PATCH.read_text()
        self.assertIn('panel_is_fresh', patch)
        self.assertIn('CLOCK_REALTIME', patch)
        self.assertIn('panel_deactivate', patch)

    def test_repaints_are_driven_by_the_frame_callback_and_stop_on_their_own(self):
        """The spec's stage one: frames from wl_surface.frame rather than a
        timer, and a chain that ends when the animation does, so the lock
        settles to a still frame instead of holding the pipeline awake."""
        patch = self.PATCH.read_text()
        self.assertIn('swaylock_panel_animating(&surface->state->panel)', patch)
        self.assertIn('surface->dirty = true;', patch)
        self.assertIn('wl_surface_damage_buffer(surface->child, panel->rect_x', patch)
        self.assertIn('swaylock_indicator_signature', patch)

    def test_the_ring_and_its_countable_highlights_go_away_under_a_panel(self):
        """swaylock highlights one arc per keypress and uses a different colour
        for backspace, so an observer can count both. A panel drawing the
        indicator area takes the whole ring with it rather than sitting beside
        a leak."""
        patch = self.PATCH.read_text()
        self.assertIn('if (!panel->hide_ring)', patch)
        self.assertIn('countable per-keystroke highlight', patch)
        panel = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/cat_panel.py'))
        self.assertIn("'ring 0'", (REPO / 'alpine/desktop/.local/lib/oldbook/cat_panel.py').read_text())
        self.assertEqual(panel['STATE_NAME'], 'cat-panel')

    def test_the_panel_fits_where_the_caption_card_is_not(self):
        """The lock has two things on it already: a clock at 40% of the height
        and a caption card in the lower-left corner whose height changes with
        the painting and the hour. A wide panel below the clock lands on the
        card, so the hearth goes above it, and it has to actually fit there."""
        scene = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py'))
        panel = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/cat_panel.py'))
        source = (REPO / 'alpine/desktop/.local/lib/oldbook/cat_panel.py').read_text()
        self.assertIn("'place above'", source)
        width, height, scale = scene['DEFAULT_GEOMETRY']
        logical_h = height // scale
        indicator_top = (int(logical_h * 0.40) - scene['INDICATOR_RADIUS']
                         - scene['INDICATOR_THICKNESS'])
        self.assertGreaterEqual(indicator_top,
                                panel['PANEL_HEIGHT'] + panel['PANEL_GAP'],
                                'the hearth must fit between the screen top and the clock')
        self.assertLessEqual(panel['PANEL_WIDTH'], width // scale - 2 * 44)

    def test_the_scene_points_the_locker_at_the_panel_in_the_private_runtime(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-lock-panel-') as directory:
            root = Path(directory)
            module = runpy.run_path(str(REPO / 'alpine/desktop/.local/lib/oldbook/lock_scene.py'))
            palette = runpy.run_path(
                str(REPO / 'alpine/desktop/.local/lib/oldbook/overlay_theme.py'))['read_palette'](root)
            # The flag is only emitted to a locker that has it. An unpatched
            # swaylock-effects exits on an unrecognised option, which the
            # launcher reads as a locker that died before readiness, so it falls
            # back to stock swaylock -- which draws none of this scene. Emitting
            # it blind replaced the whole composed lock with a bare ring.
            module['_OPTION_SUPPORT']['--indicator-panel'] = True
            arguments = module['scene_arguments'](None, palette, (1440, 900, 1), root)
            self.assertIn('--indicator-panel', arguments)
            named = Path(arguments[arguments.index('--indicator-panel') + 1])
            self.assertEqual(named, root / 'oldbook/cat-panel')
            # Nothing is created by naming it, and the plain lock is the one
            # that happens on every lock where no cat is on the keyboard.
            self.assertFalse(named.exists())

            module['_OPTION_SUPPORT']['--indicator-panel'] = False
            without = module['scene_arguments'](None, palette, (1440, 900, 1), root)
            self.assertNotIn('--indicator-panel', without)
            # Losing the panel must never cost the scene: the composed painting
            # and the caption card are still there without it.
            self.assertEqual(without.count('--effect-compose'), 2)
            self.assertNotIn('--grace', arguments)


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
            # A --help probe is a capability question, not a lock attempt, so the
            # fake answers it without counting a launch -- exactly as the real
            # binary would, and exactly as the gate in lock_scene needs.
            (fake_bin / 'swaylock-effects').write_text(
                '#!/bin/sh\n'
                'case "$1" in --help) echo "usage: swaylock"; exit 0;; esac\n'
                'echo effects >> ' + str(root / 'launches') + '\nexit 1\n')
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
