"""Keep Oldbook's desktop cards slow; system telemetry belongs in Waybar.

This preference is enforced outside panels.json so restoring an older template
does not restore its telemetry. It applies before wallpaper layout/cache lookup.
"""
import math
import re
import sys

MIN_INTERVAL = 60
MAX_INTERVAL = 300
TELEMETRY_PREFIXES = (
    'cpu', 'mem', 'swap', 'top', 'disk', 'downspeed', 'upspeed',
    'totaldown', 'totalup', 'wireless', 'fs_', 'hwmon', 'acpitemp',
    'platform', 'i2c', 'loadavg', 'freq', 'tcp', 'udp', 'threads',
    'processes', 'running_', 'entropy', 'uptime', 'nodename', 'kernel',
    'user_', 'addr', 'gw_', 'if_up', 'nvidia', 'apcupsd_load',
)
VARIABLE = re.compile(r'\$(?:\{\s*)?([A-Za-z_][A-Za-z_0-9]*)')
INTERVAL_COMMAND = re.compile(r'(\$\{\s*(?:execi|execpi|texeci|execibar|'
                              r'execigraph|execigauge)\s+)([^\s}]+)')


def slow_interval(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = MIN_INTERVAL
    if not math.isfinite(seconds):
        seconds = MIN_INTERVAL
    return max(MIN_INTERVAL, min(MAX_INTERVAL, seconds))


def quiet_document(document):
    """Omit restored system-stat cards and normalize refreshes without editing input."""
    panels = []
    for panel in document['panels']:
        variables = [match.group(1).lower() for match in VARIABLE.finditer(panel['text'])]
        if any(name.startswith(TELEMETRY_PREFIXES) for name in variables):
            print(f'oldbook-conky: omitted telemetry panel {panel["id"]}; '
                  'system stats belong in Waybar', file=sys.stderr)
            continue
        text = INTERVAL_COMMAND.sub(
            lambda match: match[1] + f'{slow_interval(match[2]):g}', panel['text'])
        panels.append(dict(panel, text=text))
    return dict(document, panels=panels,
                update_interval=slow_interval(document.get('update_interval')))
