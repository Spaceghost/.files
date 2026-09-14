import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time

repo = Path('/home/jack/.files')
result = {'test': 'headless packaged cat-hearth readiness', 'hardware_boot_tested': False}
with tempfile.TemporaryDirectory(prefix='oldbook-hearth-smoke-') as temporary:
    root = Path(temporary)
    runtime = root / 'run'
    runtime.mkdir(mode=0o700)
    subprocess.run(['tar', '-xzf', '/home/jack/.cache/oldbook-apks/oldbook-swaylock-effects-1.7.0.0-r1.apk', '-C', str(root), 'usr/bin/swaylock-effects'], check=True, capture_output=True)
    config = root / 'sway.conf'
    config.write_text('output HEADLESS-1 resolution 1000x800\nseat seat0 fallback true\n')
    panel = runtime / 'panel'
    panel.write_text('panel 1\nserial 1\nstamp ' + str(int(time.time())) + '\nstale 30\nimage hearth.png\nwidth 620\nheight 214\ngap 24\nfade 320\npoll 250\nring 0\n')
    panel.chmod(0o600)
    shutil.copyfile(repo / 'alpine/verification/cat-hearth/warming.png', runtime / 'hearth.png')
    (runtime / 'hearth.png').chmod(0o600)
    environment = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), WLR_BACKENDS='headless',
                       WLR_RENDERER='pixman', WLR_LIBINPUT_NO_DEVICES='1')
    for key in ('SWAYSOCK', 'WAYLAND_DISPLAY', 'DISPLAY'):
        environment.pop(key, None)
    locker = None
    with (root / 'sway.log').open('w') as swaylog, (root / 'locker.log').open('w') as locklog:
        compositor = subprocess.Popen(['/usr/bin/sway', '-c', str(config)], env=environment,
                                      stdout=swaylog, stderr=swaylog)
        try:
            deadline = time.monotonic() + 10
            displays = []
            while time.monotonic() < deadline:
                displays = [path for path in runtime.glob('wayland-*') if path.is_socket()]
                if displays or compositor.poll() is not None:
                    break
                time.sleep(.05)
            if not displays:
                raise RuntimeError('Private compositor failed: ' + (root / 'sway.log').read_text()[-1200:])
            environment['WAYLAND_DISPLAY'] = displays[0].name
            read_fd, write_fd = os.pipe()
            try:
                locker = subprocess.Popen([str(root / 'usr/bin/swaylock-effects'), '-R', str(write_fd),
                                           '--color', '13091f', '--clock', '--indicator-idle-visible',
                                           '--indicator-panel', str(panel)], env=environment,
                                          pass_fds=(write_fd,), stdout=locklog, stderr=locklog)
                os.close(write_fd)
                if not select.select([read_fd], [], [], 10)[0] or not os.read(read_fd, 16):
                    raise RuntimeError('Locker did not report readiness')
                time.sleep(1)
                if locker.poll() is not None:
                    raise RuntimeError('Locker exited after readiness')
                result.update(ready=True, alive_after_panel_frame=True,
                              visual_panel_confirmed=False, password_entry_tested=False)
            finally:
                os.close(read_fd)
        finally:
            if locker and locker.poll() is None:
                locker.terminate()
                locker.wait(timeout=3)
            compositor.terminate()
            compositor.wait(timeout=5)
    result['locker_log'] = (root / 'locker.log').read_text()
(repo / 'alpine/verification/catmode-recovery/hearth-smoke.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
