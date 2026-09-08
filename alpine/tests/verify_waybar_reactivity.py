#!/usr/bin/env python3
"""Exercise agents and fullscreen reactivity in an isolated native desktop."""
import ctypes
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / 'alpine/desktop/.local/bin'
OUT = ROOT / 'alpine/verification/waybar-reactivity/native'
OUT.mkdir(parents=True, exist_ok=True)


def verify():
    results = {}
    processes = []
    with tempfile.TemporaryDirectory(prefix='waybar-reactivity-') as directory:
        base = Path(directory)
        home = base / 'home'
        runtime = base / 'run'
        runtime.mkdir(mode=0o700)
        config = home / '.config'
        (config / 'waybar').mkdir(parents=True)
        (home / '.local/bin').mkdir(parents=True)
        for name in ('mbp-intel-workspaces', 'mbp-intel-fuzzel'):
            (home / '.local/bin' / name).symlink_to(BIN / name)
        # Test the actual ordinary-click branch without reading physical modifiers.
        launcher = home / '.local/bin/mbp-intel-agents'
        launcher.write_text('#!/usr/bin/python3\nimport runpy\n'
                            f'm=runpy.run_path({str(BIN / "mbp-intel-agents")!r})\n'
                            'm["launcher"].super_pressed=lambda:False\n'
                            'raise SystemExit(m["main"]())\n')
        launcher.chmod(0o755)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(config),
                   XDG_RUNTIME_DIR=str(runtime), XDG_STATE_HOME=str(base / 'state'),
                   XDG_CACHE_HOME=str(base / 'cache'), WLR_BACKENDS='headless',
                   WLR_RENDERER='pixman', WLR_HEADLESS_OUTPUTS='1',
                   PATH=str(home / '.local/bin') + ':' + os.environ['PATH'])
        for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY', 'TMUX', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        swayconf = base / 'sway.conf'
        swayconf.write_text('xwayland disable\noutput HEADLESS-1 mode 800x600\nseat seat0 fallback true\n')
        log = (OUT / 'runtime.log').open('w')

        def start(args, **kwargs):
            proc = subprocess.Popen(args, env=env, stdout=log, stderr=log, **kwargs)
            processes.append(proc)
            return proc

        def run(args, **kwargs):
            return subprocess.run(args, env=env, capture_output=True, timeout=10, **kwargs)

        def wait(predicate, timeout=10):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                value = predicate()
                if value:
                    return value
                time.sleep(.1)
            raise RuntimeError('Timed out waiting for private Waybar state')

        def ipc(command):
            result = run(['swaymsg', '-r', command], check=True)
            return json.loads(result.stdout)

        def status():
            return json.loads(run([str(BIN / 'mbp-intel-workspaces'), 'status'], check=True).stdout)

        def tree():
            return json.loads(run(['swaymsg', '-r', '-t', 'get_tree'], check=True).stdout)

        def views(node):
            if node.get('app_id'):
                yield node
            for child in node.get('nodes', []) + node.get('floating_nodes', []):
                yield from views(child)

        try:
            bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                   env=env, stdout=subprocess.PIPE, stderr=log, text=True)
            processes.append(bus)
            env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
            sway = start(['/usr/bin/sway', '-c', str(swayconf)])
            wait(lambda: list(runtime.glob('sway-ipc*.sock')))
            env['SWAYSOCK'] = str(next(runtime.glob('sway-ipc*.sock')))
            env['WAYLAND_DISPLAY'] = next(p.name for p in runtime.glob('wayland-*') if p.is_socket())
            # Synthetic foreground commands are identified through the real /proc resolver.
            child = base / 'synthetic-agent.py'
            child.write_text('import ctypes,os,sys,time\nfrom pathlib import Path\n'
                             'ctypes.CDLL(None).prctl(15,sys.argv[1].encode(),0,0,0)\n'
                             'Path(sys.argv[2]).write_text(os.ttyname(0))\n'
                             'time.sleep(120)\n')
            foot = base / 'foot.ini'
            foot.write_text('[main]\nfont=monospace:size=10\n')
            for index, kind in enumerate(('codex', 'claude')):
                start(['foot', '-c', str(foot), '--app-id', f'foot-fixture-{index}',
                       '--title', f'Synthetic {kind}', 'python3', str(child), kind, str(base / f'tty{index}')])
            wait(lambda: len(list(views(tree()))) == 2 and (base / 'tty0').exists())
            tracker = start([str(BIN / 'mbp-intel-workspaces'), 'daemon'])
            wait(lambda: status()['text'] == '✦ 2')
            results['two_real_foreground_agents_detected'] = True
            bar = json.loads((ROOT / 'alpine/desktop/.config/waybar/config.jsonc').read_text())[0]
            bar.update({'modules-left': ['custom/ai'], 'modules-center': [],
                        'modules-right': ['sway/workspaces', 'clock'],
                        'margin-left': 0, 'margin-right': 0, 'spacing': 2})
            (config / 'waybar/config.jsonc').write_text(json.dumps([bar]))
            (config / 'waybar/style.css').write_text((ROOT / 'alpine/desktop/.config/waybar/style.css').read_text())
            state = config / 'waybar/waybar-state.css'
            state.write_text('/* Written by mbp-intel-waybar-dim; edit style.css instead. */\n')
            waybar = start(['waybar'])
            wait(lambda: 'Bar configured' in (OUT / 'runtime.log').read_text())
            dimmer = start([str(BIN / 'mbp-intel-waybar-dim')])
            pointer_bin = runpy.run_path(str(ROOT / 'alpine/tests/verify_waybar_music.py'))['build_pointer'](base)
            pointer = subprocess.Popen([str(pointer_bin)], env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=log, text=True)
            processes.append(pointer)
            assert pointer.stdout.readline().strip() == 'ready'

            def pointer_event(event):
                pointer.stdin.write(event + '\n')
                pointer.stdin.flush()
                assert pointer.stdout.readline().strip() == 'ok'

            def click(button=272):
                pointer_event('move 24 16')
                pointer_event(f'press {button}')
                pointer_event(f'release {button}')

            focused = lambda: next(view['id'] for view in views(tree()) if view.get('focused'))
            first = focused()
            click()
            wait(lambda: focused() != first)
            second = focused()
            time.sleep(.3)
            click()
            wait(lambda: focused() == first)
            results['agent_bar_left_click_cycles_both_windows'] = True
            events = runtime / 'mbp-intel/codex-events'
            events.mkdir(exist_ok=True)
            now = time.time()
            (events / 'synthetic.json').write_text(json.dumps({
                'version': 1, 'event': 'approval-requested', 'observed_at': now,
                'valid_until': now + 120, 'tty': (base / 'tty0').read_text()}))
            wait(lambda: status()['class'] == 'attention')
            results['agent_attention_state_updates'] = True
            tracker.send_signal(signal.SIGSTOP)
            try:
                wait(lambda: status()['class'] == 'disconnected', timeout=8)
                assert 'No open' not in status()['tooltip']
            finally:
                tracker.send_signal(signal.SIGCONT)
            wait(lambda: status()['text'] == '✦ 2')
            results['stale_tracker_is_reported_and_fresh_count_recovers'] = True
            ipc('fullscreen enable')
            wait(lambda: 'opacity: 0.3' in state.read_text())
            pointer_event('move 400 300')
            time.sleep(.5)
            run(['grim', str(OUT / 'fullscreen-dim.png')], check=True)
            pointer_event('move 24 16')
            time.sleep(.5)
            run(['grim', str(OUT / 'fullscreen-hover.png')], check=True)
            click()
            wait(lambda: focused() != first)
            ipc(f'[con_id={first}] fullscreen disable')
            wait(lambda: 'opacity: 0.3' not in state.read_text())
            results['fullscreen_dim_hover_and_click_recover'] = True
            time.sleep(.8)  # The dim-state update reloads Waybar's widgets.
            click(273)
            def private_picker_running():
                for process in Path('/proc').glob('[0-9]*'):
                    try:
                        if ((process / 'comm').read_text().strip() == 'fuzzel'
                                and ('XDG_RUNTIME_DIR=' + str(runtime)).encode() in
                                (process / 'environ').read_bytes().split(b'\0')):
                            return True
                    except OSError:
                        continue
                return False
            wait(private_picker_running)
            time.sleep(.5)
            run(['grim', str(OUT / 'agent-menu.png')], check=True)
            run(['wtype', '-s', '200', '-k', 'Escape', '-s', '100'], check=True)
            results['agent_right_click_opens_picker'] = True
            ipc(f'[con_id={second}] kill')
            wait(lambda: status()['text'] == '✦ 1')
            assert tracker.poll() is None and dimmer.poll() is None and waybar.poll() is None
            results['closing_agent_updates_count'] = True
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
            for process in reversed(processes):
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            log.close()
            (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    verify()
