#!/usr/bin/env python3
"""The animations configuration and the launcher's compositor probe.

The probe is the part that has to be right: an older SwayFX rejects the new
commands, and a configuration it cannot parse would leave the user without a
desktop. These tests drive the real launcher script with stand-in compositors
that accept or reject the commands, and check that it only reaches for the
animation settings when they parse.
"""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / 'alpine/desktop/.local/bin/oldbook-sway'
ANIMATIONS = REPO / 'alpine/desktop/.config/swayfx/animations.conf'
RECIPE = REPO / 'alpine/packages/swayfx'

# Every command the animations file may use, with the value bounds the
# compositor enforces.
DURATION_COMMANDS = (
    'animation_duration_ms',
    'animation_open_ms',
    'animation_close_ms',
    'animation_move_ms',
    'animation_workspace_ms',
)


def settings(text):
    """Parse the animations config into a command to argument mapping."""
    parsed = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, _, value = line.partition(' ')
        parsed[name] = value.strip()
    return parsed


class AnimationsConfigTests(unittest.TestCase):
    def setUp(self):
        self.settings = settings(ANIMATIONS.read_text())

    def test_animations_are_switched_on(self):
        self.assertEqual(self.settings.get('animations'), 'enable')

    def test_workspace_style_is_a_supported_word(self):
        self.assertIn(self.settings.get('animation_workspace_style'),
                      {'slide', 'fade', 'both'})

    def test_durations_are_within_the_compositor_bounds(self):
        for command in DURATION_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, self.settings)
                value = float(self.settings[command])
                # The compositor rejects anything outside this range outright.
                self.assertGreater(value, 0)
                self.assertLessEqual(value, 5000)

    def test_motion_stays_brief_enough_to_feel_immediate(self):
        for command in ('animation_open_ms', 'animation_close_ms', 'animation_move_ms'):
            with self.subTest(command=command):
                self.assertLessEqual(float(self.settings[command]), 400)
        # The whole screen travels on a workspace switch, so it is allowed more
        # time than a single window, but not so much that it feels slow.
        self.assertLessEqual(float(self.settings['animation_workspace_ms']), 600)

    def test_no_command_outside_the_animation_family(self):
        for name in self.settings:
            with self.subTest(command=name):
                self.assertTrue(name.startswith('animation'), name)

    def test_file_carries_no_effects_that_stock_sway_shares(self):
        # effects.conf is included by the running session; keeping the two
        # apart is what stops an older binary from meeting these commands.
        text = ANIMATIONS.read_text()
        for stray in ('blur', 'corner_radius', 'shadows', 'layer_effects'):
            self.assertNotIn(stray, text)


class LauncherProbeTests(unittest.TestCase):
    """Drive oldbook-sway with fake compositors and read back its choice."""

    def run_launcher(self, accepts_animations, animations_present=True,
                     runtime_present=True, stock=False):
        with tempfile.TemporaryDirectory(prefix='oldbook-sway-probe-') as temporary:
            base = Path(temporary)
            home = base / 'home'
            runtime = base / 'run'
            binaries = base / 'bin'
            for directory in (home / '.config/swayfx', runtime, binaries):
                directory.mkdir(parents=True, exist_ok=True)

            (home / '.config/swayfx/config').write_text('# session\n')
            if animations_present:
                (home / '.config/swayfx/animations.conf').write_text(
                    ANIMATIONS.read_text())

            record = base / 'invocation.json'
            # A stand-in compositor: --validate mimics an old or new binary,
            # any other invocation records the arguments and exits.
            verdict = 0 if accepts_animations else 1
            for name in ('swayfx', 'sway'):
                script = binaries / name
                script.write_text(f'''#!/bin/sh
if [ "$1" = "--validate" ]; then
    exit {verdict}
fi
printf '%s' "$(printf '{{"binary": "{name}", "args": [')" > {record}
first=1
for argument in "$@"; do
    if [ "$first" = 1 ]; then first=0; else printf ', ' >> {record}; fi
    printf '"%s"' "$argument" >> {record}
done
printf ']}}' >> {record}
exit 0
''')
                script.chmod(script.stat().st_mode | stat.S_IEXEC)

            # The launcher hardcodes /usr/bin, so give it a private root whose
            # /usr/bin holds the stand-ins, entered with a bind-free symlink.
            usr_bin = base / 'usr/bin'
            usr_bin.mkdir(parents=True)
            for name in ('swayfx', 'sway'):
                (usr_bin / name).symlink_to(binaries / name)

            script = (LAUNCHER.read_text()
                      .replace('/usr/bin/swayfx', str(usr_bin / 'swayfx'))
                      .replace('/usr/bin/sway ', str(usr_bin / 'sway') + ' ')
                      .replace('exec dbus-run-session -- "$@"', 'exec "$@"'))
            runner = base / 'oldbook-sway'
            runner.write_text(script)
            runner.chmod(runner.stat().st_mode | stat.S_IEXEC)

            environment = dict(os.environ, HOME=str(home),
                               DBUS_SESSION_BUS_ADDRESS='unix:path=/dev/null')
            environment.pop('XDG_RUNTIME_DIR', None)
            if runtime_present:
                environment['XDG_RUNTIME_DIR'] = str(runtime)
            if stock:
                environment['OLDBOOK_STOCK_SWAY'] = '1'

            subprocess.run([str(runner)], env=environment, check=True,
                           capture_output=True, timeout=30)
            invocation = json.loads(record.read_text())
            # The stock Sway route deliberately passes no --config at all.
            if '--config' in invocation['args']:
                config = invocation['args'][invocation['args'].index('--config') + 1]
                invocation['config'] = config
                invocation['config_text'] = (
                    Path(config).read_text() if Path(config).is_file() else '')
            else:
                invocation['config'] = ''
                invocation['config_text'] = ''
            invocation['runtime'] = str(runtime)
            return invocation

    def test_patched_compositor_gets_the_animation_settings(self):
        invocation = self.run_launcher(accepts_animations=True)
        self.assertEqual(invocation['binary'], 'swayfx')
        self.assertIn('animations.conf', invocation['config_text'])
        self.assertIn('swayfx/config', invocation['config_text'])

    def test_older_compositor_never_sees_the_new_commands(self):
        invocation = self.run_launcher(accepts_animations=False)
        self.assertEqual(invocation['binary'], 'swayfx')
        self.assertTrue(invocation['config'].endswith('.config/swayfx/config'))
        self.assertNotIn('animations.conf', invocation['config_text'])

    def test_missing_animations_file_falls_back(self):
        invocation = self.run_launcher(accepts_animations=True, animations_present=False)
        self.assertTrue(invocation['config'].endswith('.config/swayfx/config'))

    def test_missing_runtime_directory_falls_back(self):
        invocation = self.run_launcher(accepts_animations=True, runtime_present=False)
        self.assertTrue(invocation['config'].endswith('.config/swayfx/config'))

    def test_stock_sway_route_is_untouched(self):
        invocation = self.run_launcher(accepts_animations=True, stock=True)
        self.assertEqual(invocation['binary'], 'sway')
        self.assertNotIn('--config', invocation['args'])

    def test_probe_file_is_not_left_behind(self):
        # A stale probe in the runtime directory would be read as session state
        # by anything that scans it; the launcher removes it either way.
        for accepts in (True, False):
            with self.subTest(accepts=accepts):
                invocation = self.run_launcher(accepts_animations=accepts)
                runtime = Path(invocation['runtime'])
                self.assertFalse((runtime / 'oldbook-animations-probe.conf').exists())


class RecipeTests(unittest.TestCase):
    def test_patch_is_a_recipe_input_with_a_checksum(self):
        apkbuild = (RECIPE / 'APKBUILD').read_text()
        self.assertIn('    window-animations.patch\n', apkbuild)
        source, _, sums = apkbuild.partition('sha512sums=')
        self.assertIn('window-animations.patch', sums)
        self.assertIn('window-animations.patch', source)

    def test_offline_builder_copies_the_patch(self):
        self.assertIn('window-animations.patch', (RECIPE / 'build-offline').read_text())

    def test_patch_touches_only_expected_files(self):
        patch = (RECIPE / 'window-animations.patch').read_text()
        touched = {line.split('/', 1)[1].strip()
                   for line in patch.splitlines() if line.startswith('+++ b/')}
        self.assertEqual(touched, {
            'include/sway/animation_manager.h',
            'include/sway/commands.h',
            'include/sway/config.h',
            'include/sway/tree/container.h',
            'include/sway/tree/workspace.h',
            'sway/animation_manager.c',
            'sway/commands.c',
            'sway/commands/animations.c',
            'sway/config.c',
            'sway/desktop/transaction.c',
            'sway/meson.build',
            'sway/sway.5.scd',
        })

    def test_every_config_command_is_documented(self):
        manual = (RECIPE / 'window-animations.patch').read_text()
        for command in DURATION_COMMANDS + ('animations', 'animation_workspace_style'):
            with self.subTest(command=command):
                self.assertIn(command, manual)


if __name__ == '__main__':
    unittest.main()
