"""Explicit local keyboard-light activation/readback; no keystrokes are injected."""
from pathlib import Path
import hashlib
import json
import os
import runpy
import subprocess
import time

repo = Path('/home/jack/.files')
record = Path(__file__).resolve().parent
helper_path = repo / 'alpine/desktop/.local/bin/oldbook-keyboard-backlight'
module = runpy.run_path(str(helper_path))
light = module['KeyboardBacklight'](Path('/sys/class/leds/smc::kbd_backlight'),
    Path.home() / '.local/state/oldbook', Path(os.environ['XDG_RUNTIME_DIR']) / 'oldbook',
    Path(os.environ['SWAYSOCK']))
report = {'source_sha256': hashlib.sha256(helper_path.read_bytes()).hexdigest(),
          'before': light.status(), 'samples': []}
assert report['before']['mode'] == 'steady' and not report['before']['running'], report['before']
peak = report['before']['level']
assert peak > 0
report['activated'] = light.command('breathe')
try:
    assert report['activated']['running']
    saved = light.level_file.read_bytes()
    saved_mtime = light.level_file.stat().st_mtime_ns
    began = time.monotonic()
    while time.monotonic() - began < 6.2:
        current = light.status()
        assert current['mode'] == 'breathing' and current['running'], current
        assert current['level'] == peak, 'Saved brightness changed during readback'
        report['samples'].append({'seconds': round(time.monotonic()-began, 4),
                                  'brightness': current['brightness']})
        time.sleep(.1)
    assert light.level_file.read_bytes() == saved
    assert light.level_file.stat().st_mtime_ns == saved_mtime
    levels = [item['brightness'] for item in report['samples']]
    assert max(levels) >= round(peak*.95) and min(levels) <= round(peak*.18), levels
    report['saved_peak_unchanged_during_animation'] = True
    report['range'] = [min(levels), max(levels)]
    report['steady'] = light.command('steady')
    deadline = time.monotonic() + 3
    while light.running() and time.monotonic() < deadline:
        time.sleep(.025)
    assert not light.running()
    assert light.read('brightness') == peak
    report['restored_peak'] = light.read('brightness')
    report['final'] = light.command('breathe')
    assert report['final']['running'] and report['final']['level'] == peak
    # Repeated login-style restore must reuse the worker.
    for _ in range(2):
        assert light.command('restore')['running']
    workers = []
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal():
            continue
        try:
            args = p.joinpath('cmdline').read_bytes().split(b'\0')
            if str(helper_path).encode() in args and b'daemon' in args and p.stat().st_uid == os.getuid():
                workers.append(int(p.name))
        except OSError:
            continue
    assert len(workers) == 1, workers
    report['worker_pids_after_repeated_restore'] = workers
    ipc = runpy.run_path(str(repo / 'alpine/desktop/.local/bin/oldbook-workspaces'))
    binding_file = repo / 'alpine/desktop/.config/sway/local.d/keyboard-backlight.conf'
    report['binding_acknowledgements'] = []
    for line in binding_file.read_text().splitlines():
        if line.startswith('bindsym --locked Shift+'):
            result = ipc['request'](Path(os.environ['SWAYSOCK']), 0, line)
            report['binding_acknowledgements'].append({'command': line, 'response': result})
            assert result and all(item.get('success') for item in result), result
    report['status'] = 'passed'
except BaseException as error:
    report['status'] = 'failed'
    report['error'] = repr(error)
    # Honor whichever level is saved now, including newer physical key input.
    light.command('steady', spawn=False)
    raise
finally:
    (record / 'live.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key != 'samples'}, indent=2))
