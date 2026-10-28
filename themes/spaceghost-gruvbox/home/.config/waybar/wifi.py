#!/usr/bin/env python3
"""Wi-Fi status with WEXT fallback for UWE5622's incomplete nl80211 telemetry."""
import html
import json
from pathlib import Path
import re
import subprocess


def command(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def render(link, wireless, address=''):
    ssid = re.search(r'^\s*SSID: (.+)$', link, re.M)
    if not ssid:
        return {'text': 'WiFi OFF', 'class': 'disconnected', 'tooltip': 'Wi-Fi disconnected or unavailable'}
    signal = re.search(r'signal:\s*(-?\d+(?:\.\d+)?)\s*dBm', link)
    # This vendor driver often omits station stats, but exposes real RSSI via WEXT.
    if signal:
        dbm = float(signal[1])
    else:
        fields = wireless.split()
        dbm = float(fields[3].rstrip('.')) if len(fields) >= 4 else None
    if dbm is None:
        return {'text': 'WiFi ?', 'class': 'linked', 'tooltip': html.escape(ssid[1])+'\nConnected; signal unavailable'}
    percent = round(max(0, min(100, 2 * (dbm + 100))))
    bars = ['▂', '▂▄', '▂▄▆', '▂▄▆█'][min(3, percent // 25)]
    state = 'weak' if percent < 40 else 'fair' if percent < 65 else 'strong'
    rate = re.search(r'tx bitrate:\s*(.+)', link)
    tooltip = f'<b>{html.escape(ssid[1])}</b>\nSignal {dbm:g} dBm · {percent}% (RSSI estimate)'
    if rate:
        tooltip += '\nTX '+html.escape(rate[1])
    if address.strip():
        tooltip += '\n'+html.escape(address.strip())
    tooltip += '\nWi-Fi association; Internet reachability is not tested.\nClick: network details'
    return {'text': f'{bars} {percent}%', 'class': state, 'tooltip': tooltip}


def main():
    interfaces = sorted(p.name for p in Path('/sys/class/net').glob('*') if (p/'wireless').exists())
    result = {'text': 'WiFi OFF', 'class': 'disconnected', 'tooltip': 'No Wi-Fi adapter'}
    for interface in interfaces:
        link = command(['iw', 'dev', interface, 'link'])
        try:
            wireless = next((s for s in Path('/proc/net/wireless').read_text().splitlines() if s.strip().startswith(interface+':')), '')
        except OSError:
            wireless = ''
        try:
            result = render(link, wireless, command(['ip', '-brief', 'address', 'show', 'dev', interface]))
        except (ValueError, IndexError):
            result = {'text': 'WiFi ?', 'class': 'linked', 'tooltip': 'Wi-Fi signal unavailable'}
        if result['class'] != 'disconnected':
            break
    print(json.dumps(result))


if __name__ == '__main__':
    main()
