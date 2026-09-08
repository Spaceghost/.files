"""Contained rendering evidence for workspace captions and flexible Waybar layout."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description='Render workspace chrome in an isolated SwayFX session.')
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--render-device', default='/dev/dri/renderD129')
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
processes = []
with tempfile.TemporaryDirectory(prefix='workspace-chrome-') as directory:
    base = Path(directory)
    runtime = base / 'run'
    runtime.mkdir(mode=0o700)
    config_home = base / 'config'
    (config_home / 'foot').mkdir(parents=True)
    shutil.copyfile(repo / 'alpine/themes/profiles/spaceghost/.config/foot/foot.ini', config_home / 'foot/foot.ini')
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), XDG_CONFIG_HOME=str(config_home),
               XDG_STATE_HOME=str(base / 'state'), WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
               WLR_RENDERER='gles2', WLR_RENDERER_ALLOW_SOFTWARE='1', WLR_RENDER_DRM_DEVICE=args.render_device)
    for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        env.pop(key, None)
    config = base / 'sway.conf'
    config.write_text('xwayland disable\noutput HEADLESS-1 mode 1440x900\noutput * bg #466780 solid_color\n'
                      'seat seat0 fallback true\ndefault_border pixel 0\ndefault_floating_border pixel 0\n'
                      'corner_radius 8\nsmart_corner_radius enable\n'
                      'layer_effects "oldbook-decoration" {\n    corner_radius 7\n}\n')
    log = (out / 'runtime.log').open('w')
    def start(argv):
        process = subprocess.Popen(argv, env=env, stdout=log, stderr=log)
        processes.append(process)
        return process
    def wait_for(test, seconds=6):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            value = test()
            if value:
                return value
            time.sleep(.1)
        raise RuntimeError('Timed out waiting for preview state')
    try:
        compositor = start(['swayfx', '-c', str(config)])
        wait_for(lambda: list(runtime.glob('sway-ipc*.sock')))
        env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
        env['WAYLAND_DISPLAY'] = next(p.name for p in runtime.glob('wayland-*') if p.is_socket())
        def ipc(kind, command=None):
            argv = ['swaymsg', '-r'] + (['-t', kind] if command is None else [command])
            return json.loads(subprocess.check_output(argv, env=env))
        def surfaces():
            return {s['namespace']: s for o in ipc('get_outputs') for s in o.get('layer_shell_surfaces', [])}
        helper = str(repo / 'alpine/desktop/.local/bin/oldbook-decoration')
        caption = start([helper, 'daemon'])
        terminal = start(['foot', '--config', str(config_home / 'foot/foot.ini'),
                          '--title', 'Codex | Workspace demo | Transparent background',
                          'sh', '-c', "printf '\033[48;2;19;9;31mWorkspace caption preview\nExplicit application background\n'; sleep 120"])
        bottom = wait_for(lambda: (s := surfaces().get('oldbook-decoration')) and s['extent']['height'] > 0 and s)
        time.sleep(1)
        subprocess.run(['grim', str(out / 'bottom.png')], env=env, check=True)
        assert 17 <= bottom['extent']['height'] <= 26, bottom
        assert bottom['effects']['corner_radius'] == 7, bottom
        subprocess.run([helper, 'right'], env=env, check=True, stdout=log)
        right = wait_for(lambda: (s := surfaces().get('oldbook-decoration')) and 0 < s['extent']['width'] < 40 and s)
        subprocess.run(['grim', str(out / 'right.png')], env=env, check=True)
        assert right['extent']['width'] >= 14, right
        subprocess.run([helper, 'bottom'], env=env, check=True, stdout=log)
        wait_for(lambda: 0 < surfaces()['oldbook-decoration']['extent']['height'] < 30)
        ipc('', 'fullscreen enable')
        time.sleep(1)
        subprocess.run(['grim', str(out / 'fullscreen.png')], env=env, check=True)
        fullscreen = ipc('get_tree')
        ipc('', 'fullscreen disable')
        # Minimal modules use the production bar's packing settings and theme CSS.
        real = json.loads((repo / 'alpine/desktop/.config/waybar/config.jsonc').read_text())[0]
        real['modules-left'] = ['custom/left']
        real['custom/left'] = {'format': 'WORKSPACES   1  2  3  4  5  6  7  8  9  10'}
        real['modules-right'] = ['custom/right']
        real['custom/right'] = {'format': 'STATUS  16:00'}
        real['group/context']['modules'] = ['sway/window']
        bar_config = base / 'bar.json'
        bar_config.write_text(json.dumps(real))
        css = (repo / 'alpine/themes/profiles/spaceghost/.config/waybar/style.css').read_text()
        css = '\n'.join(line for line in css.splitlines() if not line.startswith('@import'))
        style = base / 'style.css'
        style.write_text(css)
        bar = start(['waybar', '-c', str(bar_config), '-s', str(style)])
        wait_for(lambda: surfaces().get('top'))
        time.sleep(.7)
        subprocess.run(['grim', str(out / 'bar-content.png')], env=env, check=True)
        long_terminal = start(['foot', '--config', str(config_home / 'foot/foot.ini'),
                               '--title', 'A long focused window title ' * 24, 'sleep', '120'])
        time.sleep(1)
        subprocess.run(['grim', str(out / 'bar-long-title.png')], env=env, check=True)
        assert surfaces()['top']['extent']['width'] == 1432
        long_terminal.terminate()
        long_terminal.wait(timeout=3)
        ipc('', 'workspace 2')
        time.sleep(1)
        subprocess.run(['grim', str(out / 'bar-empty.png')], env=env, check=True)
        assert caption.poll() is None and bar.poll() is None
        (out / 'evidence.json').write_text(json.dumps({'bottom': bottom, 'right': right,
            'fullscreen_tree': fullscreen, 'bar': surfaces().get('top'),
            'checks': ['bottom is compact', 'right has readable width', 'fullscreen rendered',
                       'content-sized middle rendered', 'empty middle rendered']}, indent=2))
        print(out)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        log.close()
