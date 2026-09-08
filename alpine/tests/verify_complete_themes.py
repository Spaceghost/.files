#!/usr/bin/env python3
"""Render real themed terminals and bars in a private compositor and HOME."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]


def verify(identity, output):
    profile = REPO / 'alpine/themes/profiles' / identity
    descriptor = json.loads((REPO / 'alpine/themes' / (identity + '.json')).read_text())
    output.mkdir(parents=True, exist_ok=False)
    paintings = sorted((REPO / 'alpine/assets/gallery/themes' / identity).glob('*.png'))
    if not paintings:
        raise RuntimeError('Theme has no painting')
    with tempfile.TemporaryDirectory(prefix='complete-theme-') as temporary:
        base = Path(temporary)
        home, runtime = base / 'home', base / 'run'
        home.mkdir()
        runtime.mkdir(mode=0o700)
        (home / '.config').symlink_to(profile / '.config')
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
                   WLR_RENDERER='pixman', GTK_USE_PORTAL='0', NO_AT_BRIDGE='1')
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
            env.pop(key, None)
        config = output / 'sway.conf'
        config.write_text(f'''xwayland disable
output HEADLESS-1 mode 1440x900
output * bg "{paintings[-1]}" fill
seat seat0 fallback true
include "{profile / '.config/sway/theme.conf'}"
include "{profile / '.config/swayfx/effects.conf'}"
for_window [app_id="theme-preview"] floating enable
for_window [app_id="theme-preview"] resize set 760 430
for_window [app_id="theme-preview"] move position center
''')
        processes = []
        with (output / 'runtime.log').open('w') as log:
            def spawn(command):
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                           start_new_session=True)
                processes.append(process)
                return process
            def wait_for(predicate):
                for _ in range(160):
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError('Preview process exited; see runtime.log')
                    value = predicate()
                    if value:
                        return value
                    time.sleep(.05)
                raise RuntimeError('Preview timed out')
            try:
                subprocess.run(['swayfx', '--validate', '--config', str(config)], env=env,
                               stdout=log, stderr=log, check=True, timeout=15)
                spawn(['swayfx', '--config', str(config)])
                wait_for(lambda: list(runtime.glob('sway-ipc*.sock')))
                env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
                env['WAYLAND_DISPLAY'] = next(p.name for p in runtime.glob('wayland-*') if p.is_socket())
                bar = json.loads((profile / '.config/waybar/config.jsonc').read_text())[0]
                bar.update({'output': 'HEADLESS-1', 'modules-left': ['custom/ghost', 'sway/workspaces'],
                            'modules-center': [], 'modules-right': ['clock']})
                bar['custom/ghost'] = {'format': descriptor['name']}
                bar['clock'] = {'format': '{:%H:%M}'}
                bar_config = output / 'waybar.json'
                bar_config.write_text(json.dumps(bar, indent=2))
                spawn(['waybar', '--config', str(bar_config), '--style', str(profile / '.config/waybar/style.css')])
                sample = output / 'sample.txt'
                design = descriptor['design']
                sample.write_text('\n  ' + descriptor['name'] + '\n\n  ' +
                    '\n  '.join(f'{key}: {value}' for key, value in design.items()) +
                    '\n\n  Complete desktop profile · native Foot and Waybar\n')
                spawn(['foot', '--config', str(profile / '.config/foot/foot.ini'),
                       '--app-id=theme-preview', '--title=' + descriptor['name'],
                       'sh', '-c', 'cat "$1"; exec sleep 30', 'preview', str(sample)])
                wait_for(lambda: 'Bar configured' in (output / 'runtime.log').read_text())
                time.sleep(1.5)
                subprocess.run(['grim', str(output / 'desktop.png')], env=env, check=True, timeout=30)
                tree = subprocess.check_output(['swaymsg', '-r', '-t', 'get_tree'], env=env, text=True)
                (output / 'tree.json').write_text(tree)
                (output / 'design.json').write_text(json.dumps(descriptor['design'], indent=2))
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                for process in processes:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()


if __name__ == '__main__':
    if not os.environ.get('MBP_INTEL_THEME_PRIVATE_BUS'):
        raise SystemExit(subprocess.call(['dbus-run-session', sys.executable, __file__, *sys.argv[1:]],
                         env=dict(os.environ, MBP_INTEL_THEME_PRIVATE_BUS='1')))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('themes', nargs='+')
    args = parser.parse_args()
    for identity in args.themes:
        verify(identity, args.output.resolve() / identity)
