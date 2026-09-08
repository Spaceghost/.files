"""Drive the real keyboard LED in ambient mode from a fake sensor, with private state dirs."""
import json, runpy, sys, tempfile, threading, time
from pathlib import Path
HELPER = Path('/home/jack/.files/alpine/desktop/.local/bin/oldbook-keyboard-backlight')
Klass = runpy.run_path(str(HELPER))['KeyboardBacklight']
led = Path('/sys/class/leds/smc::kbd_backlight')
session = sys.argv[1]
with tempfile.TemporaryDirectory(prefix='ambient-live-') as tmp:
    base = Path(tmp)
    state, runtime, sensor = base / 'state', base / 'runtime', base / 'light'
    state.mkdir(); runtime.mkdir()
    (state / 'keyboard-backlight').write_text('255\n')
    sensor.write_text('(2,0)\n')
    helper = Klass(led, state, runtime, session=session, sensor=sensor)
    before = int((led / 'brightness').read_text())
    real = Path('/sys/devices/platform/applesmc.768/light').read_text().strip()
    helper.command('ambient', spawn=False)
    stop = threading.Event()
    worker = threading.Thread(target=helper.serve, args=(stop,), daemon=True)
    worker.start()
    samples = []
    phases = [(0.0, '(2,0)'), (8.0, '(600,0)'), (20.0, '(1,0)')]
    started = time.monotonic()
    while time.monotonic() - started < 32.0:
        elapsed = time.monotonic() - started
        for at, value in phases:
            if abs(elapsed - at) < 0.13:
                sensor.write_text(value + '\n')
        samples.append((round(elapsed, 2), int((led / 'brightness').read_text())))
        time.sleep(0.25)
    stop.set(); worker.join(timeout=5)
    after = int((led / 'brightness').read_text())
    (led / 'brightness').write_text(f'{before}\n')
    print(json.dumps(dict(real_sensor_reading=real, hardware_before=before, hardware_after_worker_stop=after,
                          hardware_restored_to=int((led / 'brightness').read_text()),
                          temp_saved_level=int((state / 'keyboard-backlight').read_text()),
                          phases=phases, samples=samples)))
