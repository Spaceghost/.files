#!/usr/bin/env python3
"""Run terminal clients inside a private headless SwayFX session and screenshot them.

Modelled on alpine/themes/concepts/ghost-observatory/preview: private runtime
directory, private D-Bus, headless wlroots backend, nothing touches the live desktop.

usage: headless.py --output DIR --client ghostty|foot --command 'shell command' [--wait 4]
       [--app-id ID] [--ghostty-config FILE] [--foot-config FILE] [--env KEY=VALUE ...]
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time

REPO = Path('/home/jack/.files')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--client', choices=('ghostty', 'foot'), required=True)
    parser.add_argument('--command', required=True, help='run through sh -c inside the terminal')
    parser.add_argument('--wait', type=float, default=4.0)
    parser.add_argument('--app-id', default='com.oldbook.headless')
    parser.add_argument('--ghostty-config', type=Path)
    parser.add_argument('--foot-config', type=Path)
    parser.add_argument('--env', action='append', default=[])
    parser.add_argument('--render-device', default='/dev/dri/renderD128')
    parser.add_argument('--size', default='1440x900')
    parser.add_argument('--shots', type=int, default=1, help='screenshots, one per --wait interval')
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    art = REPO / 'alpine/assets/spaceghost.png'
    config = output / 'sway.conf'
    config.write_text(f'''xwayland disable
output HEADLESS-1 mode {args.size}
output * bg "{art}" fill
seat seat0 fallback true
focus_follows_mouse no
mouse_warping none
include "{REPO / 'alpine/desktop/.config/sway/theme.conf'}"
include "{REPO / 'alpine/desktop/.config/swayfx/effects.conf'}"
default_border pixel 0
for_window [app_id="{args.app_id}"] floating enable, resize set width 1200 px height 760 px, move position center
''')
    processes = []
    with tempfile.TemporaryDirectory(prefix='headless-terminal-') as runtime:
        env = os.environ.copy()
        env.update(XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='1',
                   WLR_RENDERER='gles2', WLR_RENDERER_ALLOW_SOFTWARE='1',
                   WLR_RENDER_DRM_DEVICE=args.render_device, NO_AT_BRIDGE='1', GTK_USE_PORTAL='0',
                   XDG_CONFIG_HOME=str(output / 'config-home'))
        (output / 'config-home').mkdir(exist_ok=True)
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'TMUX',
                    'OLDBOOK_SPLASH', 'TERM_PROGRAM'):
            env.pop(key, None)
        for item in args.env:
            key, _, value = item.partition('=')
            env[key] = value
        log = (output / 'runtime.log').open('w')

        def spawn(command, **kwargs):
            process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                       start_new_session=True, **kwargs)
            processes.append(process)
            return process

        def ipc(command, kind=None):
            invocation = ['swaymsg', '-r'] + (['-t', kind] if kind else []) + ([command] if command else [])
            return json.loads(subprocess.check_output(invocation, env=env, text=True))

        def walk(node):
            yield node
            for child in node.get('nodes', []) + node.get('floating_nodes', []):
                yield from walk(child)

        try:
            bus_socket = Path(runtime) / 'bus'
            bus_config = Path(runtime) / 'bus.conf'
            bus_config.write_text(f'''<busconfig><type>session</type>
<listen>unix:path={bus_socket}</listen><auth>EXTERNAL</auth>
<policy context="default"><allow send_destination="*"/>
<allow receive_sender="*"/><allow own="*"/></policy></busconfig>''')
            spawn(['dbus-daemon', '--nofork', '--config-file=' + str(bus_config)])
            for _ in range(100):
                if bus_socket.exists():
                    break
                time.sleep(.02)
            env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(bus_socket)
            subprocess.run(['/usr/bin/swayfx', '--validate', '-c', str(config)], env=env,
                           stdout=log, stderr=log, check=True)
            compositor = spawn(['/usr/bin/swayfx', '-c', str(config)])
            for _ in range(100):
                sockets = list(Path(runtime).glob('sway-ipc*.sock'))
                displays = [p for p in Path(runtime).glob('wayland-*') if p.suffix != '.lock']
                if sockets and displays:
                    env.update(SWAYSOCK=str(sockets[0]), WAYLAND_DISPLAY=displays[0].name)
                    break
                if compositor.poll() is not None:
                    raise RuntimeError('compositor exited; see runtime.log')
                time.sleep(.05)
            else:
                raise RuntimeError('compositor did not start')
            time.sleep(.5)
            client_log = (output / f'{args.client}.log').open('w')
            if args.client == 'ghostty':
                launcher = ['ghostty', '--gtk-single-instance=false', '--class=' + args.app_id,
                            '--window-decoration=none']
                if args.ghostty_config:
                    launcher.append('--config-file=' + str(args.ghostty_config.absolute()))
                launcher += ['-e', 'sh', '-c', args.command]
            else:
                launcher = ['foot', '--app-id=' + args.app_id]
                if args.foot_config:
                    launcher += ['-c', str(args.foot_config.absolute())]
                launcher += ['sh', '-c', args.command]
            client = subprocess.Popen(launcher, env=env, stdout=client_log, stderr=client_log,
                                      start_new_session=True)
            processes.append(client)
            for _ in range(200):
                if any(n.get('app_id') == args.app_id for n in walk(ipc(None, 'get_tree'))):
                    break
                if client.poll() is not None:
                    raise RuntimeError('client exited early; see logs')
                time.sleep(.05)
            else:
                raise RuntimeError('client did not map')
            ipc(f'[app_id="{args.app_id}"] focus')
            for shot in range(args.shots):
                time.sleep(args.wait)
                target = output / (f'screenshot-{shot}.png' if args.shots > 1 else 'screenshot.png')
                subprocess.run(['grim', '-o', 'HEADLESS-1', str(target)], env=env, check=True)
                print('screenshot', target)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for process in reversed(processes):
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            log.close()


if __name__ == '__main__':
    main()
