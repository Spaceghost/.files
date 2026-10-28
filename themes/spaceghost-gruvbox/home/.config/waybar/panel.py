#!/usr/bin/python3
"""Small-panel controls. Standard library only; no daemon or network polling."""
import collections
import calendar
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def cpu():
    values = list(map(int, read('/proc/stat').splitlines()[0].split()[1:9]))
    return sum(values), sum(values[3:5])


def memory_stats():
    values = {}
    for line in read('/proc/meminfo').splitlines():
        key, value = line.split(':', 1)
        values[key] = int(value.split()[0])
    return {
        'total': values.get('MemTotal', 1),
        'available': values.get('MemAvailable', values.get('MemFree', 0)),
        'free': values.get('MemFree', 0),
        'cache': max(0, values.get('Cached', 0) - values.get('Shmem', 0)) + values.get('Buffers', 0) + values.get('SReclaimable', 0),
    }


def health():
    memory = {}
    for line in read('/proc/meminfo').splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0])
    total = memory.get('MemTotal', 1)
    used = total - memory.get('MemAvailable', total)
    temperatures = []
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            temperatures.append((read(zone/'type'), float(read(zone/'temp')) / 1000))
        except ValueError:
            pass
    temperature = max((v for _, v in temperatures), default=None)
    disk = shutil.disk_usage(Path.home())
    return used, total, temperature, temperatures, disk


def status(once=False):
    previous = cpu()
    history = collections.deque(maxlen=5)
    while True:
        time.sleep(0.2 if once or not history else 10)
        current = cpu()
        delta = current[0] - previous[0]
        usage = max(0, min(100, round(100 * (1 - (current[1] - previous[1]) / max(delta, 1)))))
        previous = current
        history.append('▁▂▃▄▅▆▇█'[min(7, usage * 8 // 101)])
        used, total, temperature, temperatures, disk = health()
        memory = memory_stats()
        pressure = used / total
        hot = temperature is not None and temperature >= 80
        state = 'critical' if pressure >= .95 or (temperature is not None and temperature >= 90) else 'warning' if pressure >= .85 or hot else 'normal'
        tooltip = '\n'.join([
            '<b>SYSTEM</b>',
            f'CPU     {usage}%   {"".join(history)}',
            f'RAM available  {memory["available"]/1024:.0f} / {total/1024:.0f} MiB',
            f'Unused {memory["free"]/1024:.0f} MiB · reclaimable cache {memory["cache"]/1024:.0f} MiB',
            'Available already includes reclaimable cache; do not add it twice.',
            f'Home    {disk.free/1073741824:.1f} GiB free ({disk.used/disk.total:.0%} used)',
            f'Load    {read("/proc/loadavg").split()[0]}',
            *[f'{html.escape(name)}  {value:.0f}°C' for name, value in temperatures],
            '\nSuper+Ctrl+Shift+P: details · Super+Ctrl+P: panel',
        ])
        # Keep the essentials visible on a keyboard-only device.
        thermal = f' {temperature:.0f}°' if temperature is not None else ''
        text = f'{memory["available"]/1024:.0f}M'
        print(json.dumps({'text': text, 'tooltip': tooltip, 'class': state}), flush=True)
        if once:
            return


def command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ''


def details(section):
    if section == 'calendar':
        today = datetime.now()
        print(today.strftime('%A, %d %B %Y  %H:%M') + '\n')
        print(calendar.TextCalendar().formatmonth(today.year, today.month))
    elif section == 'keys':
        print('SPACEGHOST / KEYBOARD\n')
        print('F1–F6: programmable action buttons')
        print('Shift+F1: view and change their mappings')
        print('Super+Ctrl+P    Panel / search actions')
        print('Super+Ctrl+Shift+P  System details')
        print('Super+D         Search applications')
        print('Super+Return    Terminal')
        print('Super+1 … 0     Workspaces 1 … 10')
        print('Super+Tab       Previous workspace')
        print('\nPanel: type to filter, arrows to select,')
        print('Enter to run, Escape to dismiss.')
        print('\nBar details include CPU, temperature and storage.')
        print('RAM = available MiB, including reclaimable cache.')
    elif section == 'network':
        print('NETWORK\n')
        print(command(['ip', '-brief', 'address']))
        print('\nROUTES\n' + command(['ip', 'route']))
        print('\nWIRELESS\n' + (read('/proc/net/wireless') or 'No wireless telemetry'))
    else:
        used, total, temperature, temperatures, disk = health()
        print('SPACEGHOST / SYSTEM\n')
        memory = memory_stats()
        print(f'RAM available: {memory["available"]/1024:.0f} / {total/1024:.0f} MiB')
        print(f'Unused: {memory["free"]/1024:.0f} MiB; reclaimable cache: {memory["cache"]/1024:.0f} MiB')
        print('Available includes cache; it is not counted twice.')
        print(f'Home: {disk.free/1073741824:.1f} GiB free')
        print(f'Load: {read("/proc/loadavg")}')
        print('\n' + '\n'.join(f'{n}: {v:.0f}°C' for n, v in temperatures))
        print('\nUPTIME\n' + command(['uptime']))
    try:
        input('\nPress Enter to close…')
    except EOFError:
        pass


def launch(args):
    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def menu():
    actions = {
        'Apps            Search applications': ['fuzzel'],
        'YouTube         Search and floating player': [str(Path.home()/'.local/bin/yt')],
        'Terminal        Open foot': ['foot'],
        'Processes       CPU and memory': ['foot', '-e', 'htop'],
        'System          Temperature and storage': ['foot', '-e', sys.executable, __file__, 'system'],
        'Network         Addresses and routes': ['foot', '-e', sys.executable, __file__, 'network'],
        'Audio           ALSA mixer': ['foot', '-e', 'alsamixer'],
        'Calendar        Date and month': ['foot', '-e', sys.executable, __file__, 'calendar'],
        'Keyboard        Shortcuts and bar legend': ['foot', '-e', sys.executable, __file__, 'keys'],
        'Buttons         Remap F1–F6': [str(Path.home()/'.local/bin/sharkdeck-keys'), 'map'],
        'Screenshot      Save to Downloads': [sys.executable, __file__, 'screenshot'],
        'Previous        Last workspace': ['swaymsg', 'workspace', 'back_and_forth'],
        'Reload bar      Apply bar configuration': [str(Path.home()/'.local/bin/spaceghost-waybar'), '--restart', '-b', 'bar-0'],
    }
    if command(['playerctl', '-l']):
        actions.update({
            'Play / pause    Media': ['playerctl', 'play-pause'],
            'Next track      Media': ['playerctl', 'next'],
            'Previous track  Media': ['playerctl', 'previous'],
        })
    result = subprocess.run(['fuzzel', '--dmenu', '--prompt', 'Panel > ', '--width', '40', '--lines', '7'], input='\n'.join(actions), text=True, capture_output=True)
    if result.returncode == 0 and result.stdout.strip() in actions:
        launch(actions[result.stdout.strip()])


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'menu'
    if action == 'status':
        try:
            status('--once' in sys.argv)
        except BrokenPipeError:
            pass
    elif action == 'has-battery':
        sys.exit(0 if any(read(p/'type') == 'Battery' for p in Path('/sys/class/power_supply').glob('*')) else 1)
    elif action == 'menu':
        menu()
    elif action in ('system', 'network', 'calendar', 'keys'):
        details(action)
    elif action == 'screenshot':
        destination = Path.home()/'Downloads'
        destination.mkdir(exist_ok=True)
        subprocess.run(['grim', str(destination/datetime.now().strftime('screenshot-%Y%m%d-%H%M%S.png'))], check=True)
