#!/usr/bin/env python3
"""Run the synthetic workspace typography fixture in a private Xvfb session."""
import argparse, json, os
from pathlib import Path
import resource, select, signal, subprocess, sys, tempfile
parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if os.environ.get('OLDBOOK_STRATA_GTK_PRIVATE_BUS') != '1':
    env = dict(os.environ)
    env.pop('DBUS_SESSION_BUS_ADDRESS', None)
    env['OLDBOOK_STRATA_GTK_PRIVATE_BUS'] = '1'
    os.execvpe('dbus-run-session', ['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env)
args.output.mkdir(parents=True, exist_ok=False)
with tempfile.TemporaryDirectory(prefix='strata-workspace-gtk-') as directory:
    base = Path(directory)
    env = dict(os.environ)
    for key, name in [('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'), ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data')]:
        path = base / name
        path.mkdir(mode=448)
        env[key] = str(path)
    for key in ('DISPLAY', 'SWAYSOCK', 'WAYLAND_DISPLAY'):
        env.pop(key, None)
    env.update(NO_AT_BRIDGE='1', GTK_USE_PORTAL='0', G_DEBUG='fatal-warnings', GDK_BACKEND='x11')
    read_fd, write_fd = os.pipe()
    with (args.output / 'xvfb.log').open('w') as server_log:
        server = subprocess.Popen(['Xvfb', '-displayfd', str(write_fd), '-nolisten', 'tcp', '-screen', '0', '980x120x24', '-ac'], env=env, pass_fds=(write_fd,), stdin=subprocess.DEVNULL, stdout=server_log, stderr=server_log, start_new_session=True)
        os.close(write_fd)
        try:
            if not select.select([read_fd], [], [], 10)[0]:
                raise RuntimeError('private Xvfb did not start')
            display = os.read(read_fd, 64).decode().strip()
            if not display.isdigit():
                raise RuntimeError('invalid Xvfb display')
            env['DISPLAY'] = ':' + display
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            with (args.output / 'gtk.log').open('w') as log:
                result = subprocess.run([str(args.binary.resolve())], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=20)
            evidence = {'exit_code': result.returncode, 'binary': str(args.binary.resolve()), 'isolation': 'private Xvfb, D-Bus, HOME and XDG directories; no host windows', 'fatal_gtk_warnings': True, 'core_dumps': False}
            (args.output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
            print(json.dumps(evidence))
            print((args.output / 'gtk.log').read_text())
        finally:
            os.close(read_fd)
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait()
