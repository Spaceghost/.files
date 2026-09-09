"""What the machine's temperatures permit, and what the fans are allowed to do.

This exists because one feature on this desktop deliberately makes the laptop
hot and deliberately holds its fans down, and the rule for that feature is that
every number which decides "too hot" lives in one readable place rather than
inline in the loop that is generating the heat.

Three sensor families are read, and all three are required:

    cpu      the Intel package and cores, via the coretemp hwmon. This is the
             fast one: it moves in seconds and it is what a load actually
             pushes. Tjmax on this part trips at 84 C and the critical alarm at
             100 C, so every ceiling here is far below both.
    battery  the Apple SMC's TB*T cells. A warm battery is the only part of
             this machine that a long gentle heating can actually damage, and
             a closed lid is exactly the geometry that traps heat against it.
    skin     the SMC's Ts0P and Ts1P: the palm rest and the underside. This is
             the one the cat is lying on, so its ceiling is a comfort limit
             rather than an electrical one.

             Only the *P points are read. Measured on this machine with the
             package at 82 C and both fans at maximum, Ts0P was 31.8 C and
             Ts1P 31.0 C -- a plausible chassis surface -- while Ts0S read
             43.8 C and Ts1S 45.3 C, which no palm rest on a fan-pinned laptop
             is. The *S keys are the SMC's own internal skin figures, not a
             measurement of the surface, and treating them as one would cut
             every sitting short for a reason that was never true.

             The skin ceiling will usually not be the binding constraint, and
             that is fine: it is here for the failure this feature invents, a
             machine whose chassis is hot because a cat and a shut lid have
             blanketed it while the cores themselves look calm.

A missing sensor is never treated as a cool sensor. `readings()` returns None
for anything it cannot read and `verdict()` answers 'stop' for a None, so an
unplugged module, a renamed hwmon or a permissions change all end the heating
rather than blinding it.

Both roots are environment-overridable so the whole ladder can be exercised
against a synthetic sysfs tree, the way OLDBOOK_POWER_ROOT does for the power
posture. Nothing here writes anything; writes to the fans are the privileged
helper's job alone.
"""
import os
from pathlib import Path

# The Apple SMC labels each temperature; these are the ones worth a ceiling.
BATTERY_LABELS = ('TB0T', 'TB1T', 'TB2T', 'TBXT')
SKIN_LABELS = ('Ts0P', 'Ts1P')
# A sensor reporting one of these is disconnected on this board, not freezing.
IMPLAUSIBLE_BELOW = 0.0
IMPLAUSIBLE_ABOVE = 125.0

# Every ceiling, in one table, for the two regimes bed mode can run under.
#
# open   The lid is up and the machine cools convectively as it always does.
#        The load ceiling is 72 C: twelve degrees below Tjmax, and low enough
#        that the machine is never anywhere near throttling.
# closed The lid is shut, most of the airflow path with it, and the panel is
#        pressed against the keyboard. Everything tightens, and the fans are
#        allowed back much earlier because they are the only cooling left.
#
# The orderings inside a regime are load-bearing and are asserted in the tests:
#     target < fan_release <= cpu_resume < cpu_ceiling < abort
#     fan_hold_entry < fan_release
# so the fans always come back *before* the load is cut, and the load is cut
# well before anything approaches the hardware's own limits.
REGIMES = {
    'open': {
        'cpu_target': 60.0,
        'cpu_ceiling': 72.0,
        'cpu_resume': 66.0,
        'fan_hold_entry': 55.0,
        'fan_release': 66.0,
        'battery_ceiling': 45.0,
        'skin_ceiling': 40.0,
        'abort': 80.0,
    },
    'closed': {
        'cpu_target': 54.0,
        'cpu_ceiling': 65.0,
        'cpu_resume': 58.0,
        'fan_hold_entry': 50.0,
        'fan_release': 58.0,
        'battery_ceiling': 42.0,
        'skin_ceiling': 38.0,
        'abort': 72.0,
    },
}
FAMILIES = ('cpu', 'battery', 'skin')


def smc_root():
    """The Apple SMC platform directory: battery, skin and the fan controls."""
    return Path(os.environ.get('OLDBOOK_SMC_ROOT', '/sys/devices/platform/applesmc.768'))


def hwmon_root():
    return Path(os.environ.get('OLDBOOK_HWMON_ROOT', '/sys/class/hwmon'))


def regime(lid_closed):
    """The ceilings that apply right now. A shut lid is a stricter regime."""
    return dict(REGIMES['closed' if lid_closed else 'open'])


def _millidegrees(path):
    try:
        value = int(path.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None
    if not IMPLAUSIBLE_BELOW < value < IMPLAUSIBLE_ABOVE:
        # applesmc reports -127 C for a point this board does not populate.
        return None
    return value


def hwmon_named(name, root=None):
    """Every hwmon directory reporting this chip name, in a stable order."""
    root = hwmon_root() if root is None else Path(root)
    found = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        try:
            if (entry / 'name').read_text().strip() == name:
                found.append(entry)
        except OSError:
            continue
    return found


def cpu_celsius(root=None):
    """The hottest core or package the coretemp driver reports, or None.

    The package runs a degree or two above the cores under load, so taking the
    maximum means the ceiling is enforced against the hottest thing measured
    rather than an average that lags it.
    """
    values = []
    for chip in hwmon_named('coretemp', root):
        try:
            inputs = sorted(chip.glob('temp*_input'))
        except OSError:
            continue
        for entry in inputs:
            reading = _millidegrees(entry)
            if reading is not None:
                values.append(reading)
    return max(values) if values else None


def labelled_celsius(labels, root=None):
    """The hottest SMC sensor carrying one of these labels, or None.

    Labels rather than indices: temp10_input is TC1f on this machine and
    something else on the next one, and a silently renumbered sensor must not
    quietly become a different ceiling.
    """
    root = smc_root() if root is None else Path(root)
    wanted = set(labels)
    values = []
    try:
        entries = sorted(root.glob('temp*_label'))
    except OSError:
        return None
    for entry in entries:
        try:
            label = entry.read_text().strip()
        except OSError:
            continue
        if label not in wanted:
            continue
        reading = _millidegrees(entry.with_name(entry.name[:-len('_label')] + '_input'))
        if reading is not None:
            values.append(reading)
    return max(values) if values else None


def readings(smc=None, hwmon=None):
    """Every family bed mode needs, with None for anything unreadable."""
    return {'cpu': cpu_celsius(hwmon),
            'battery': labelled_celsius(BATTERY_LABELS, smc),
            'skin': labelled_celsius(SKIN_LABELS, smc)}


def unreadable(values):
    """The families that did not answer. Any entry here is a stop condition."""
    return sorted(name for name in FAMILIES if values.get(name) is None)


def verdict(values, limits, coasting=False):
    """May the heating run right now: 'run', 'coast' or 'stop'.

    'stop' is terminal for the sitting and means the fans go back to automatic
    immediately; 'coast' only pauses the load and is left by cooling below
    cpu_resume, which is why the caller passes back whether it is already
    coasting. Reasons are returned rather than logged so the published record
    can say exactly which ceiling answered.
    """
    missing = unreadable(values)
    if missing:
        return 'stop', ['unreadable: ' + ', '.join(missing)]
    reasons = []
    cpu, battery, skin = values['cpu'], values['battery'], values['skin']
    if cpu >= limits['abort']:
        reasons.append(f'cpu {cpu:.1f}C at or past the abort line {limits["abort"]:.0f}C')
    if battery >= limits['battery_ceiling']:
        reasons.append(f'battery {battery:.1f}C at or past {limits["battery_ceiling"]:.0f}C')
    if skin >= limits['skin_ceiling']:
        reasons.append(f'skin {skin:.1f}C at or past {limits["skin_ceiling"]:.0f}C')
    if reasons:
        return 'stop', reasons
    if cpu >= limits['cpu_ceiling']:
        return 'coast', [f'cpu {cpu:.1f}C at or past the ceiling {limits["cpu_ceiling"]:.0f}C']
    if coasting and cpu > limits['cpu_resume']:
        return 'coast', [f'cpu {cpu:.1f}C still above the resume line {limits["cpu_resume"]:.0f}C']
    return 'run', []


def fan_verdict(values, limits, holding):
    """What the fans should be doing: 'hold', 'release' or 'keep'.

    Entering the hold is only ever allowed from cool, and leaving it is
    one-way for the caller: a released hold is not re-taken during a sitting,
    because a machine that has already reached fan_release once will reach it
    again and a fan that oscillates between manual and automatic is worse than
    one that simply runs.
    """
    missing = unreadable(values)
    if missing:
        return 'release', ['unreadable: ' + ', '.join(missing)]
    cpu = values['cpu']
    if holding:
        if cpu >= limits['fan_release']:
            return 'release', [f'cpu {cpu:.1f}C at or past the fan release '
                               f'{limits["fan_release"]:.0f}C']
        return 'keep', []
    if cpu <= limits['fan_hold_entry']:
        return 'hold', []
    return 'keep', [f'cpu {cpu:.1f}C above the quiet entry {limits["fan_hold_entry"]:.0f}C']


def duty(values, limits, previous, gain=0.04, slew=0.08):
    """How hard to push, as a fraction of one core-second per second.

    A plain proportional controller around cpu_target with a slew limit. It is
    deliberately slack: the point is a warm chassis over minutes, so a slow
    approach that never overshoots into the ceiling beats a tight loop that
    keeps bouncing the load on and off.
    """
    cpu = values.get('cpu')
    if cpu is None:
        return 0.0
    wanted = previous + gain * (limits['cpu_target'] - cpu)
    wanted = min(previous + slew, max(previous - slew, wanted))
    return min(1.0, max(0.0, wanted))


def lid_closed(path=None):
    """True, False, or None when the lid cannot be read at all.

    ACPI publishes the state as text rather than only as an evdev event, which
    matters because the daemon needs the answer at startup, not just when the
    lid next moves. None is handled by the caller as the strict regime: not
    knowing whether the lid is shut is not a reason to use the loose ceilings.
    """
    root = Path(path or os.environ.get('OLDBOOK_LID_ROOT', '/proc/acpi/button/lid'))
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            text = (entry / 'state').read_text()
        except OSError:
            continue
        state = text.split(':', 1)[-1].strip().lower()
        if state in ('open', 'closed'):
            return state == 'closed'
    return None
