#!/usr/bin/env python3
"""WalnutPi UWE5622: prefer non-DFS 5 GHz, keep 2.4 GHz fallback, persist no powersave."""
import argparse
import datetime
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--restore', type=Path, help='restore backup directory printed by a previous run')
args = parser.parse_args()
if os.geteuid() != 0:
    parser.error('run using doas or sudo')
model = Path('/proc/device-tree/model').read_text().strip('\x00')
if 'WalnutPi' not in model:
    parser.error('this tuning is specific to WalnutPi; no files changed')
config = Path('/etc/wpa_supplicant/wpa_supplicant.conf')
hook = Path('/etc/network/if-up.d/spaceghost-wifi')
if args.restore:
    backup = args.restore.resolve()
    shutil.copy2(backup/'wpa_supplicant.conf', config)
    if (backup/'hook').exists():
        shutil.copy2(backup/'hook', hook)
    else:
        hook.unlink(missing_ok=True)
else:
    source = config.read_text()
    backup = Path('/var/lib/spaceghost-wifi')/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(config, backup/'wpa_supplicant.conf')
    os.chmod(backup/'wpa_supplicant.conf', 0o600)
    if hook.exists():
        shutil.copy2(hook, backup/'hook')
    if 'ctrl_interface=' not in source:
        source = 'ctrl_interface=/run/wpa_supplicant\n'+source
    if 'id_str="spaceghost-prefer-5ghz"' not in source:
        blocks = re.findall(r'(?m)^network\s*=\s*\{[^}]*\}', source)
        preferred = []
        for block in blocks:
            # Preserve explicitly frequency- or BSSID-pinned networks.
            if re.search(r'(?m)^\s*(freq_list|bssid)\s*=', block):
                continue
            found = re.search(r'(?m)^\s*priority\s*=\s*(-?\d+)', block)
            priority = int(found[1]) if found else 0
            body = re.sub(r'(?m)^\s*(priority|id_str)\s*=.*$', '', block[:-1])
            preferred.append(body+'\n    priority='+str(priority+10)+'\n    freq_list=5180 5200 5220 5240 5745 5765 5785 5805 5825\n    id_str="spaceghost-prefer-5ghz"\n}')
        if preferred:
            source += '\n# Spaceghost 5GHz preferences (original networks remain fallback)\n'+'\n'.join(preferred)+'\n'
    config.write_text(source)
    os.chmod(config, 0o600)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text('#!/bin/sh\n# UWE5622 interactive stability: keep Wi-Fi power saving disabled.\ncase "${IFACE:-}" in\n  wlan*) /usr/sbin/iw dev "$IFACE" set power_save off ;;\nesac\n')
    hook.chmod(0o755)
    print('Backup:', backup)
    print('Undo: doas python3', Path(__file__).resolve(), '--restore', backup)
for proc in Path('/proc').glob('[0-9]*'):
    try:
        if (proc/'comm').read_text().strip() == 'wpa_supplicant':
            os.kill(int(proc.name), signal.SIGHUP)
    except (OSError, ValueError):
        pass
subprocess.run(['iw', 'dev', 'wlan0', 'set', 'power_save', 'off'], check=False)
print('Configuration reloaded; credentials were retained locally. Verify association with wpa_cli status.')
