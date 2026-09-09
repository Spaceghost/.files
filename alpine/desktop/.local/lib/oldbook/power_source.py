"""One power posture for the whole desktop, and the ladder effects shed by.

Before this, two helpers knew where the power came from and each read sysfs its
own way: `oldbook-battery-cue` for its thresholds and `oldbook-conky` for its
battery line. Everything else on the desktop ran the same whether the machine
was plugged in or not, so the eyecandy cost the same either way.

A posture is the desktop's answer to one question, and every effect asks it the
same way. The thresholds are deliberately the ones the battery cue and the
Waybar module already use, so the desktop never disagrees with itself about
what "low" means.
"""
import json
import os
from pathlib import Path

# Ordered from most permissive to least; the ladder below reads by this order.
POSTURES = ('mains', 'battery', 'battery-low', 'battery-critical')
WARNING = 25
CRITICAL = 10

# The last posture at which each effect still runs. An effect that is missing
# runs everywhere on purpose: forgetting to register a new helper must never
# silently switch it off, only registering it can.
LADDER = {
    'gallery-drift': 'mains',
    'gallery-generation': 'mains',
    'phosphor': 'mains',
    'shaders': 'mains',
    'workspace-atmosphere': 'mains',
    'blur': 'battery',
    'cava': 'battery',
    'gallery-rotation': 'battery',
    'keyboard-breath': 'battery',
    'wallpaper-crossfade': 'battery',
    'window-animations': 'battery',
    'window-ghosts': 'battery',
    'letterpress': 'battery-low',
    'terminal-progress': 'mains',
    'window-context-detail': 'battery-low',
    'reading-cards': 'battery-low',
    'screen-corners': 'battery-low',
    'sound-cues': 'battery-low',
}


def power_root():
    return Path(os.environ.get('OLDBOOK_POWER_ROOT', '/sys/class/power_supply'))


def read_supplies(root=None):
    """What the hardware says: mains presence, charge and whether it is filling.

    A machine with no battery at all reports mains, which is the right posture
    for a desktop: nothing should shed anything on a machine that cannot run
    out. An unreadable supply is skipped rather than guessed at.
    """
    root = power_root() if root is None else root
    mains, capacity, charging = None, None, False
    if not root.is_dir():
        return {'mains': True, 'capacity': None, 'charging': False}
    for entry in sorted(root.iterdir()):
        try:
            kind = (entry / 'type').read_text().strip()
            if kind == 'Mains':
                online = (entry / 'online').read_text().strip() == '1'
                mains = online if mains is None else (mains or online)
            elif kind == 'Battery':
                status = (entry / 'status').read_text().strip()
                charge = int((entry / 'capacity').read_text().strip())
                capacity = charge if capacity is None else min(capacity, charge)
                charging = charging or status in ('Charging', 'Full')
        except (OSError, ValueError):
            continue
    if mains is None:
        # No mains supply is exposed; a charging battery still proves the cord.
        mains = True if capacity is None else charging
    return {'mains': mains, 'capacity': capacity, 'charging': charging}


def measured_posture(root=None):
    """The posture the hardware alone asks for, ignoring any override."""
    supplies = read_supplies(root)
    if supplies['mains']:
        return 'mains'
    charge = supplies['capacity']
    if charge is None:
        return 'battery'
    if charge <= CRITICAL:
        return 'battery-critical'
    if charge <= WARNING:
        return 'battery-low'
    return 'battery'


def override_path():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base) / 'oldbook/power-posture.json'


def read_override():
    """A posture the user asked for by hand, or None to follow the hardware.

    Kept deliberately visible: `show` always reports an override, and it can
    only make the desktop quieter than the hardware asks, never louder. Being
    plugged in is not permission to override an empty battery back up to mains.
    """
    try:
        record = json.loads(override_path().read_text())
        posture = record.get('posture')
        return posture if posture in POSTURES else None
    except (OSError, ValueError, AttributeError):
        return None


def write_override(posture):
    path = override_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    if posture is None:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        return
    if posture not in POSTURES:
        raise ValueError(f'Unknown posture: {posture}')
    temporary.write_text(json.dumps({'posture': posture}) + '\n')
    temporary.replace(path)


def posture(root=None):
    """What the desktop should behave as, hardware and override together."""
    measured = measured_posture(root)
    asked = read_override()
    if asked is None:
        return measured
    return max(measured, asked, key=POSTURES.index)


def allows(effect, current=None):
    """May this effect run right now?

    Unknown effects are allowed: the ladder is a list of things that shed, not
    a permit list, so a helper is never disabled by omission.
    """
    current = posture() if current is None else current
    limit = LADDER.get(effect, POSTURES[-1])
    return POSTURES.index(current) <= POSTURES.index(limit)


def shed(current):
    """Effects the ladder switches off at this posture, for reporting."""
    return sorted(name for name in LADDER if not allows(name, current))


def state_path(runtime=None):
    runtime = runtime or os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise RuntimeError('XDG_RUNTIME_DIR is required to publish the power posture')
    directory = Path(runtime) / 'oldbook'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory / 'power.json'


def publish(record, runtime=None):
    path = state_path(runtime)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)


def published(runtime=None):
    """The running daemon's record, or a fresh reading when it is not running.

    Subscribers never have to care whether the daemon is up: a desktop with no
    power service still gets a correct answer, only without the change hooks.
    """
    try:
        return json.loads(state_path(runtime).read_text())
    except (OSError, ValueError, RuntimeError):
        return describe()


def describe(root=None):
    current = posture(root)
    supplies = read_supplies(root)
    return {'posture': current, 'measured': measured_posture(root),
            'override': read_override(), 'shed': shed(current), **supplies}
