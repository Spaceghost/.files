import importlib.machinery
import importlib.util
import json
import inspect
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'bazzite/bin/oldbook-bazzite-profile'


def load_helper():
    loader = importlib.machinery.SourceFileLoader('bazzite_profile', str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class BazziteProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()

    def run_profile(self, *arguments):
        return subprocess.run(
            [str(HELPER), *arguments, '--target', str(self.home)],
            cwd=REPO, text=True, capture_output=True, timeout=20)

    def test_preview_is_read_only_and_reports_managed_changes(self):
        result = self.run_profile('preview')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('add .config/sway/config', result.stdout)
        self.assertIn('add .local/bin/oldbook-wallpaper', result.stdout)
        self.assertFalse((self.home / '.local/state/oldbook').exists())

    def test_override_bytecode_is_not_deployed(self):
        module = load_helper()
        overrides = Path(self.tmp.name) / 'overrides'
        cache = overrides / '.local/bin/__pycache__'
        cache.mkdir(parents=True)
        (cache / 'helper.pyc').write_bytes(b'host bytecode')
        (overrides / '.local/bin/loose.pyc').write_bytes(b'host bytecode')
        (overrides / '.local/bin/kept').write_text('#!/bin/sh\nexit 0\n')
        with mock.patch.object(module, 'OVERRIDES', overrides):
            desired = module.desired_files(self.home)
        self.assertIn(Path('.local/bin/kept'), desired)
        self.assertFalse(any('__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo')
                             for path in desired))

    def test_apply_uses_safe_journal_and_rollback_restores_original(self):
        original = self.home / '.config/sway/config'
        original.parent.mkdir(parents=True)
        original.write_text('my existing sway config\n')

        applied = self.run_profile('apply')

        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(original.is_symlink())
        config = original.read_text()
        self.assertNotIn('output eDP-1 mode', config)
        self.assertIn('~/.local/bin/oldbook-bazzite-session', config)
        self.assertNotIn('oldbook-session\n', config)
        backup = Path(applied.stdout.strip().split('Backup: ', 1)[1])
        manifest = json.loads((backup / 'manifest.json').read_text())
        self.assertEqual(manifest['status'], 'complete')

        rolled_back = self.run_profile('rollback', str(backup))
        self.assertEqual(rolled_back.returncode, 0, rolled_back.stderr)
        self.assertFalse(original.is_symlink())
        self.assertEqual(original.read_text(), 'my existing sway config\n')

    def test_changed_profile_gets_new_immutable_overlay_and_can_rollback(self):
        module = load_helper()
        first = {Path('.config/example'): (b'first\n', 0o644)}
        second = {Path('.config/example'): (b'second\n', 0o644)}
        deployer = module.load_deployer()
        with mock.patch.object(module, 'desired_files', return_value=first):
            old_overlay = module.materialize(self.home)
            deployer.deploy(self.home, old_overlay)
        with mock.patch.object(module, 'desired_files', return_value=second):
            new_overlay = module.materialize(self.home)
            backup = deployer.deploy(self.home, new_overlay)

        destination = self.home / '.config/example'
        self.assertNotEqual(old_overlay, new_overlay)
        self.assertEqual(destination.read_text(), 'second\n')
        deployer.rollback(self.home, backup)
        self.assertEqual(destination.read_text(), 'first\n')
        self.assertEqual(destination.resolve(), old_overlay / '.config/example')

    def test_profile_excludes_alpine_services_and_uses_user_systemd(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)

        self.assertFalse((self.home / '.local/bin/oldbook-session').exists())
        self.assertFalse((self.home / '.local/bin/oldbook-firewall-ui').exists())
        self.assertFalse((self.home / '.local/bin/oldbook-panel-status').exists())
        target = self.home / '.config/systemd/user/oldbook-session.target'
        self.assertIn('oldbook-waybar.service', target.read_text())
        for name in ('oldbook-waybar.service', 'oldbook-swaync.service',
                     'oldbook-swayidle.service', 'oldbook-wallpaper.service'):
            self.assertTrue((target.parent / name).is_symlink(), name)

        joined = '\n'.join(path.read_text() for path in target.parent.iterdir())
        for forbidden in ('pipewire', 'wireplumber', 'dbus-daemon', 'privacyctl',
                          'opensnitch', 'rc-service', '/etc/init.d', 'doas apk'):
            self.assertNotIn(forbidden, joined.lower())

    def test_session_bootstrap_imports_sway_environment_before_target(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        fake_bin = Path(self.tmp.name) / 'bin'
        fake_bin.mkdir()
        log = Path(self.tmp.name) / 'calls'
        for command in ('systemctl', 'dbus-update-activation-environment'):
            script = fake_bin / command
            script.write_text('#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*" >> "$CALL_LOG"\n')
            script.chmod(0o755)
        environment = {
            'PATH': str(fake_bin) + ':/usr/bin:/bin',
            'CALL_LOG': str(log),
            'DISPLAY': ':1',
            'WAYLAND_DISPLAY': 'wayland-9',
            'SWAYSOCK': '/run/user/1000/sway.sock',
            'XDG_CURRENT_DESKTOP': 'sway',
            'XDG_SESSION_TYPE': 'wayland',
        }
        result = subprocess.run(
            [str(self.home / '.local/bin/oldbook-bazzite-session')],
            env=environment, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text().splitlines(), [
            'systemctl --user import-environment DISPLAY WAYLAND_DISPLAY SWAYSOCK XDG_CURRENT_DESKTOP XDG_SESSION_TYPE',
            'dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY SWAYSOCK XDG_CURRENT_DESKTOP XDG_SESSION_TYPE',
            'systemctl --user start oldbook-session.target',
        ])

    def test_waybar_uses_per_user_glibc_module_without_losing_art_controls(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)

        config = json.loads((self.home / '.config/waybar/config.jsonc').read_text())
        top = config[0]
        self.assertIn('cffi/art', top['modules-left'])
        self.assertEqual(
            top['cffi/art']['module_path'],
            str(self.home / '.local/lib/oldbook/oldbook-art.so'))
        self.assertEqual(top['cffi/art'].get('command'),
                         '~/.local/bin/oldbook-wallpaper')
        self.assertNotIn('custom/radio', top)
        self.assertNotIn('custom/firewall', top)
        self.assertNotIn('group/transmission', top['group/status']['modules'])

    def test_repo_dependent_gallery_helpers_keep_the_source_checkout(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)

        module = load_helper()
        overlay = module.overlay_directory(self.home)
        self.assertEqual((overlay.parent / 'repo').resolve(), REPO)
        for name in ('oldbook-wallpaper', 'oldbook-gallery-prompts', 'oldbook-conky'):
            text = (self.home / '.local/bin' / name).read_text()
            self.assertIn("parents[3] / 'repo'", text)
        wallpaper = (self.home / '.local/bin/oldbook-wallpaper').read_text()
        self.assertNotIn("REPO / 'alpine/desktop/.local/bin/oldbook-control'", wallpaper)
        self.assertIn("Path(__file__).resolve().parent / 'oldbook-control'", wallpaper)

    def test_every_retained_oldbook_sway_binding_has_a_deployed_helper(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)

        config = (self.home / '.config/sway/config').read_text()
        helpers = {token for token in config.replace("'", ' ').replace('"', ' ').split()
                   if token.startswith('~/.local/bin/oldbook-')}
        self.assertTrue(helpers)
        self.assertTrue((self.home / '.local/bin/oldbook-conky').is_symlink())
        for helper in helpers:
            name = helper.removeprefix('~/.local/bin/')
            self.assertTrue((self.home / '.local/bin' / name).exists(), name)

    def test_gallery_and_media_helpers_have_their_fuzzel_wrapper(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue((self.home / '.local/bin/oldbook-fuzzel').is_symlink())
        self.assertTrue((self.home / '.local/bin/oldbook-scripture').is_symlink())

    def test_deployed_shortcut_wrapper_imports_checkout_project(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        fake_bin = Path(self.tmp.name) / 'superhold-bin'
        fake_bin.mkdir()
        (fake_bin / 'superhold').write_text('#!/bin/sh\nprintf "Superhold fixture %s\\n" "$*"\n')
        (fake_bin / 'superhold').chmod(0o755)
        result = subprocess.run(
            [str(self.home / '.local/bin/oldbook-shortcuts'), '--help'],
            env={'PATH': str(fake_bin) + ':/usr/bin:/bin'},
            text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Superhold fixture --help\n')

    def test_bazzite_lock_uses_stock_swaylock_supported_readiness_flags(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        path = self.home / '.local/bin/oldbook-lock'
        loader = importlib.machinery.SourceFileLoader('bazzite_lock', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        lock = importlib.util.module_from_spec(spec)
        loader.exec_module(lock)
        self.assertEqual(inspect.signature(lock.acquire_lock).parameters['command'].default,
                         'swaylock')
        help_text = subprocess.run(['swaylock', '--help'], text=True,
                                   capture_output=True, timeout=5)
        help_text = help_text.stdout + help_text.stderr
        flags = [value for value in lock.lock_arguments(9) if value.startswith('-')]
        for flag in flags:
            self.assertIn(flag.split('=', 1)[0], help_text)

    def test_deployed_overlay_theme_reads_the_checkout_palette(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)

        path = self.home / '.local/lib/oldbook/overlay_theme.py'
        loader = importlib.machinery.SourceFileLoader('deployed_overlay_theme', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        theme = importlib.util.module_from_spec(spec)
        loader.exec_module(theme)
        current = (REPO / 'alpine/themes/current').read_text().strip()
        expected = json.loads((REPO / 'alpine/themes' / f'{current}.json').read_text())
        self.assertEqual(theme.THEMES, REPO / 'alpine/themes')
        self.assertEqual(theme.read_palette()['background'], expected['palette']['background'])

    def test_check_detects_target_drift_and_missing_native_module(self):
        before = self.run_profile('check', '--skip-runtime')
        self.assertNotEqual(before.returncode, 0)
        self.assertIn('profile is not applied', before.stdout)
        self.assertIn('missing Fedora-built artwork module', before.stdout)

        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        module = self.home / '.local/lib/oldbook/oldbook-art.so'
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_bytes(b'not an ELF')
        after = self.run_profile('check', '--skip-runtime')
        self.assertNotEqual(after.returncode, 0)
        self.assertIn('artwork module is not an ELF shared object', after.stdout)

    def test_check_reports_direct_menu_media_and_session_dependencies(self):
        applied = self.run_profile('apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        module = self.home / '.local/lib/oldbook/oldbook-art.so'
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_bytes(b'\x7fELF\x02\x01Fedora fixture')
        fake_path = Path(self.tmp.name) / 'runtime-path'
        fake_path.mkdir()
        (fake_path / 'python3').symlink_to('/usr/bin/python3')

        result = subprocess.run(
            [str(HELPER), 'check', '--target', str(self.home)],
            cwd=REPO, env={'PATH': str(fake_path)}, text=True, capture_output=True,
            timeout=20)
        self.assertNotEqual(result.returncode, 0)
        for command in ('dbus-update-activation-environment', 'ghostty', 'btop',
                        'thunar', 'pavucontrol', 'ip', 'loginctl', 'less', 'mpv',
                        'mpvpaper', 'yt-dlp', 'wl-copy', 'playerctl', 'nmcli',
                        'swaylock', 'superhold', 'fossil', 'firefox', 'jq'):
            self.assertIn(command, result.stdout)
        self.assertIn('missing Fossil repository database', result.stdout)

    def test_check_rejects_content_changed_through_a_managed_link(self):
        module = load_helper()
        desired = {Path('.config/example'): (b'expected\n', 0o644)}
        with mock.patch.object(module, 'desired_files', return_value=desired):
            overlay = module.materialize(self.home)
            module.load_deployer().deploy(self.home, overlay)
            self.assertEqual(module.changes(self.home),
                             [('current', Path('.config/example'))])
            (self.home / '.config/example').write_text('corrupted revision\n')
            self.assertEqual(module.changes(self.home),
                             [('update', Path('.config/example'))])

    def test_allowlist_rejects_native_and_private_source_paths(self):
        module = load_helper()
        for relative in module.source_paths():
            text = str(relative)
            self.assertFalse(text.startswith('alpine/security/'), text)
            self.assertNotIn('__pycache__', text)
            self.assertNotIn('auth.json', text)
            self.assertFalse(text.endswith(('.so', '.apk', '.pyc', '.pyo')), text)


if __name__ == '__main__':
    unittest.main()
