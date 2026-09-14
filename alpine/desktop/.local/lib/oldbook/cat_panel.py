"""The hearth: what the lock screen shows while the machine is warming a cat.

Bed mode only ever runs while the session is locked, and a session lock surface
covers everything -- no layer-shell surface can be put above it -- so anything
the user is to see about it has to be drawn by the locker. `swaylock-effects`
grew `--indicator-panel` for exactly that: it draws a PNG under its clock,
described by a short text file, and it runs none of our code to do it. This
module is the writer of that pair. It renders the picture and writes the state
file; the locker validates, blits, and never executes anything from here.

Three things it must be, in the order they matter.

*Honest.* This is a picture of a laptop being deliberately heated with its fans
held down. The embers are a real temperature on a stated scale, the scale's top
is the temperature at which the sitting is abandoned, and both ceilings that
are not the CPU's -- the battery and the palm rest -- are printed with their own
limits beside their own readings. Nothing implies the warming goes on forever:
the STOP mark is drawn before the fire is lit, during the countdown, so the
limit is visible before anything happens rather than after.

*Silent about the password.* The panel is a function of the cat record and the
clock and of nothing else. It never sees a keystroke, it is quantised to whole
degrees and whole seconds so it cannot carry fine timing, and while it is up it
asks the locker to hide its own ring, which takes the countable per-keypress
highlight off the screen with it. The one input-shaped thing here is that a cat
lying on the keyboard is what summons the panel at all, and that judgement needs
five keys held for two seconds plus corroboration, which no typed password is.

*Still.* Continuous ambient motion is not welcome on this desktop. Nothing here
loops: a frame is drawn when a reading changes, which is every two seconds at
most, and the locker eases between two of them over a third of a second and
then stops drawing entirely. On battery -- where bed mode does not run at all,
so the panel is only ever explaining why -- even the ease is off.
"""
import hashlib
import json
import os
from pathlib import Path
import time

# The ladder entry this asks for. `cat-bed` already sheds everything below
# mains; this one is about the drawing, so that a panel which is only saying
# "not warming, you are on battery" is a still picture rather than an animation.
LADDER_EFFECT = 'cat-hearth'

STATE_NAME = 'cat-panel'
# Two slots, alternating, so the locker's outgoing image still exists while it
# cross-fades away from it. One file would fade a picture into itself.
IMAGE_NAMES = ('cat-hearth-a.png', 'cat-hearth-b.png')

# The panel goes *above* the clock, and its size is set by the room there.
# `lock_scene` puts the indicator at 40% of the output height with a radius of
# 172 and a thickness of 8, so on this 1440x900 logical panel the indicator's
# own strip starts at y=180 and everything above it is empty. 150 + 14 leaves a
# 16-pixel margin from the top of the screen. Below the clock is not available:
# the caption card is 560 wide at the lower-left corner and 252 tall for the
# current painting, which leaves 64 pixels of clear height under the ring and a
# height that changes with every painting and every hour's Scripture.
PANEL_WIDTH = 620            # logical pixels
PANEL_HEIGHT = 150
PANEL_GAP = 14
# The locker forgets a panel this many seconds after its stamp, so a cat daemon
# that dies takes the hearth off the screen without anyone having to tell it.
STALE_SECONDS = 12
MAINS_FADE_MS = 320
MAINS_POLL_MS = 250
QUIET_FADE_MS = 0
QUIET_POLL_MS = 2000

# The gauge. Thirty degrees is below anything a running CPU reports, so the
# hearth is never empty and never full at rest; the top of the scale is the
# regime's own abort line, which is the temperature at which the sitting ends.
SCALE_FLOOR = 30.0
EMBER_CELLS = 28
FLAME_STEPS = 5              # a flame is a whole number of blocks, never a curve

MONO_FONT = 'JetBrainsMono Nerd Font'
CAT_GLYPH = '\U000f011b'     # nf-md-cat
FAN_GLYPH = '\U000f0210'     # nf-md-fan
GHOST_GLYPH = '\U000f02a0'


def runtime_directory(runtime=None):
    base = runtime or os.environ.get('XDG_RUNTIME_DIR') or str(Path.home() / '.local/state')
    directory = Path(base) / 'oldbook'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def state_path(runtime=None):
    return runtime_directory(runtime) / STATE_NAME


def enabled(document=None):
    """The panel's own switch, beside the feature's.

    It lives in the interaction registry rather than in `breath.json` because
    that file's reader keeps a fixed set of keys and belongs to another feature;
    a switch nobody can find is worse than a switch in a second place. Missing
    means on, so a config written before this existed still shows the hearth.
    """
    if os.environ.get('OLDBOOK_CAT_PANEL', '') in ('0', 'off', 'no'):
        return False
    if not isinstance(document, dict):
        return True
    return bool(document.get('panel', True))


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _number(value):
    return value if isinstance(value, (int, float)) and value == value else None


def describe(record, ceilings=None, posture='mains'):
    """What the hearth should say right now, from the cat daemon's own record.

    Returns None when there is nothing to show, which is the instruction to take
    the panel off the screen entirely. Every number here comes out of the record
    the daemon already published: no sensor is read a second time, so the panel
    can never disagree with the thing deciding whether to keep heating.
    """
    if not isinstance(record, dict):
        return None
    if not (record.get('present') or record.get('guard_engaged')):
        return None
    if not record.get('locked') or not record.get('enabled'):
        return None
    bed = record.get('bed') if isinstance(record.get('bed'), dict) else {}
    thermalish = record.get('thermal') if isinstance(record.get('thermal'), dict) else {}
    limits = ceilings or thermalish.get('ceilings') or {}
    if not limits:
        return None
    values = thermalish.get('temperatures') or bed.get('temperatures') or {}

    countdown = _number(bed.get('seconds_left'))
    arming = bool(bed.get('arming')) and countdown is not None
    running = bool(bed.get('running'))
    coasting = bool(bed.get('coasting'))
    if arming:
        mode = 'countdown'
    elif running:
        mode = 'coasting' if coasting else 'warming'
    else:
        mode = 'holding'

    stop = _number(limits.get('abort')) or 80.0
    panel = {
        'mode': mode,
        'floor': SCALE_FLOOR,
        'target': _number(limits.get('cpu_target')) or 60.0,
        'ease': _number(limits.get('cpu_ceiling')) or 72.0,
        'stop': stop,
        'battery_ceiling': _number(limits.get('battery_ceiling')) or 45.0,
        'skin_ceiling': _number(limits.get('skin_ceiling')) or 40.0,
        'cpu': _number(values.get('cpu')),
        'battery': _number(values.get('battery')),
        'skin': _number(values.get('skin')),
        # Whole seconds and whole degrees. The panel is redrawn only when one of
        # these changes, so nothing on screen carries a finer clock than that.
        'countdown': int(countdown) + 1 if arming else None,
        'countdown_left': _clamp(countdown / max(1e-6, _number(bed.get('arming_seconds')) or 20.0))
                          if arming else 0.0,
        'duty': _clamp(_number(bed.get('duty')) or 0.0),
        'fans_held': bool(bed.get('fans_held')),
        'regime': thermalish.get('regime') or bed.get('regime') or 'open',
        'lid': record.get('lid') or 'unknown',
        'reason': bed.get('refusal') or bed.get('stopped_reason') or '',
        'work': bed.get('work'),
        'animated': posture == 'mains',
    }
    return panel


def _headline(panel):
    if panel['mode'] == 'countdown':
        return 'CATBED · WORK STARTS IN'
    if panel['mode'] == 'warming':
        return 'CATBED · USEFUL WORK'
    if panel['mode'] == 'coasting':
        return 'CATBED · COOLING'
    return 'CATBED · IDLE'


def _notice(panel):
    if panel['mode'] == 'countdown':
        return 'THERMAL CHECK · FANS AUTOMATIC'
    if panel['mode'] == 'coasting':
        return 'THE CEILING WAS REACHED · LOAD OFF'
    if panel['mode'] == 'warming':
        work = panel.get('work')
        return (f'WORK · {str(work).upper()[:32]}' if work
                else 'NO USEFUL WORK REPORTED')
    reason = str(panel.get('reason') or 'nothing to do').upper()
    return reason[:40]


def content_key(panel):
    """A stable digest of everything drawn, and nothing that is not.

    The panel's serial is bumped from this, so the locker's cross-fade fires
    exactly once per visible change and never on a rewritten timestamp.
    """
    drawn = {
        'mode': panel['mode'],
        'headline': _headline(panel),
        'notice': _notice(panel),
        'countdown': panel['countdown'],
        'countdown_step': round(panel['countdown_left'], 2),
        'embers': ember_count(panel),
        'flame': flame_blocks(panel),
        'cpu': None if panel['cpu'] is None else round(panel['cpu']),
        'battery': None if panel['battery'] is None else round(panel['battery']),
        'skin': None if panel['skin'] is None else round(panel['skin']),
        'ceilings': [panel['floor'], panel['target'], panel['ease'], panel['stop'],
                     panel['battery_ceiling'], panel['skin_ceiling']],
        'fans_held': panel['fans_held'],
        'lid': panel['lid'],
        'regime': panel['regime'],
    }
    return hashlib.sha256(json.dumps(drawn, sort_keys=True).encode()).hexdigest()[:16]


# ---- the mapping, on its own so a test can state it -------------------------


def scale_position(panel, celsius):
    """Where a temperature sits along the hearth, 0 at the floor, 1 at the stop."""
    if celsius is None:
        return 0.0
    span = max(1e-6, panel['stop'] - panel['floor'])
    return _clamp((celsius - panel['floor']) / span)


def ember_count(panel):
    """How many of the hearth's cells are lit: the CPU temperature, quantised.

    Lit cells are heat that is really there. An unreadable CPU sensor lights
    nothing, because a sensor that will not answer is a stop condition for the
    heating and must not read as a cold machine.
    """
    if panel['cpu'] is None:
        return 0
    return int(round(scale_position(panel, panel['cpu']) * EMBER_CELLS))


def flame_blocks(panel):
    """How tall the flames stand: the duty the controller is actually pushing.

    Separate from the embers on purpose. Coasting drops the flames to nothing
    while the embers stay lit, which is the truth: the load is off and the
    machine is still hot.
    """
    if panel['mode'] in ('countdown', 'holding'):
        return 0
    return int(round(_clamp(panel['duty']) * FLAME_STEPS))


# ---- drawing ----------------------------------------------------------------


def _rgb(colour, fallback='#ebdbb2'):
    text = (colour or fallback).lstrip('#')
    if len(text) != 6:
        text = fallback.lstrip('#')
    return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _rounded(context, x, y, width, height, radius):
    from math import pi
    context.new_sub_path()
    context.arc(x + width - radius, y + radius, radius, -pi / 2, 0)
    context.arc(x + width - radius, y + height - radius, radius, 0, pi / 2)
    context.arc(x + radius, y + height - radius, radius, pi / 2, pi)
    context.arc(x + radius, y + radius, radius, pi, 3 * pi / 2)
    context.close_path()


def render(panel, palette, scale, target):
    """Draw the hearth to an ARGB PNG at the output scale. Returns the path.

    Pango and cairo, the same pair `lock_scene.render_caption` uses, so the card
    and this panel are the same object in two places rather than two designs.
    """
    import cairo
    import gi
    gi.require_version('Pango', '1.0')
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import Pango, PangoCairo

    target = Path(target)
    accent = _rgb(palette.get('accent'), '#fabd2f')
    secondary = _rgb(palette.get('accent_secondary') or palette.get('accent'), '#fabd2f')
    alarm = _rgb(palette.get('foreground'), '#ebdbb2')
    muted = _rgb(palette.get('muted'), '#928374')
    border = _rgb(palette.get('border'), '#504945')
    ground = _rgb(palette.get('background_hard'), '#1d2021')

    width, height, padding, radius = PANEL_WIDTH, PANEL_HEIGHT, 18, 14
    inner = width - 2 * padding
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                 int(width * scale), int(height * scale))
    context = cairo.Context(surface)
    context.scale(scale, scale)

    def text(markup, x, y, align='left', box=None):
        box = inner if box is None else box
        x = max(padding - 8, min(width - padding - box + 8, x))
        layout = PangoCairo.create_layout(context)
        layout.set_width(int(box) * Pango.SCALE)
        layout.set_alignment({'left': Pango.Alignment.LEFT,
                              'right': Pango.Alignment.RIGHT,
                              'center': Pango.Alignment.CENTER}[align])
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_markup(markup, -1)
        context.move_to(x, y)
        PangoCairo.show_layout(context, layout)
        return layout.get_pixel_extents()[1].height

    def mono(body, size, colour, weight=500, spacing=1400):
        red, green, blue = colour
        hexed = '#%02x%02x%02x' % tuple(int(round(c * 255)) for c in (red, green, blue))
        return (f'<span font_family="{MONO_FONT}" size="{size}" weight="{weight}" '
                f'letter_spacing="{spacing}" foreground="{hexed}">{body}</span>')

    # The slab, in the caption card's own vocabulary: a translucent charcoal
    # ground with one hairline and no outline pixel.
    _rounded(context, 0, 0, width, height, radius)
    context.set_source_rgba(*ground, 0.80)
    context.fill_preserve()
    context.set_source_rgba(*border, 0.85)
    context.set_line_width(1)
    context.stroke()

    # Row one: who is here, and what the fans are doing.
    text(mono(f'{CAT_GLYPH}  CAT ON THE KEYBOARD', 8600, accent, 600, 2400),
         padding, padding - 4)
    fans = (mono(f'{FAN_GLYPH} FANS HELD', 8000, accent, 500) if panel['fans_held']
            else mono('FANS AUTOMATIC', 8000, muted, 500))
    text(fans, padding, padding - 4, align='right')

    # Row two: the hearth itself.
    hearth_top = padding + 16
    hearth_height = 52
    grate = hearth_top + hearth_height
    # The scale stops short of the right edge on purpose: the abort line is
    # then a wall with its own label beside it rather than a mark crushed into
    # the corner, and no reading can ever be drawn past where the sitting ends.
    bar = inner - 78
    cell = bar / EMBER_CELLS
    lit = ember_count(panel)
    flame = flame_blocks(panel)
    ease_at = padding + bar * scale_position(panel, panel['ease'])

    # Every mark that limits this sitting, drawn whether or not it is near:
    # the ceiling is part of the picture, not a thing that appears at the end.
    marks_from = hearth_top + (26 if panel['mode'] in ('countdown', 'holding') else 4)
    for value, colour, alpha in ((panel['target'], muted, 0.55),
                                 (panel['ease'], muted, 0.75),
                                 (panel['stop'], alarm, 0.85)):
        at = padding + bar * scale_position(panel, value)
        context.set_source_rgba(*colour, alpha)
        context.rectangle(at, marks_from, 1 if value != panel['stop'] else 2,
                          grate + 4 - marks_from)
        context.fill()

    for index in range(EMBER_CELLS):
        x = padding + index * cell
        block = max(2.0, cell - 3)
        centre = x + block / 2
        if index < lit:
            heat = index / max(1, EMBER_CELLS - 1)
            colour = alarm if centre > ease_at else tuple(
                s + (a - s) * heat for s, a in zip(secondary, accent))
            context.set_source_rgba(*colour, 0.55 + 0.45 * heat)
            context.rectangle(x, grate - 5, block, 5)
            context.fill()
            if flame:
                # A flame is whole blocks with a fixed profile: taller towards
                # the middle of the lit bed, narrowing and brightening as it
                # rises, and identical from one frame to the next. Nothing here
                # moves unless a reading moved.
                near = 1.0 - abs((index + 0.5) / max(1, lit) - 0.5) * 1.4
                blocks = max(1, int(round(flame * max(0.15, near))))
                for step in range(blocks):
                    tall = 8
                    top = grate - 6 - (step + 1) * tall
                    taper = 1.0 - 0.16 * step
                    tip = (step + 1) / max(1, blocks)
                    lick = tuple(c + (a - c) * 0.55 * tip for c, a in zip(colour, alarm))
                    context.set_source_rgba(*lick, max(0.14, 0.62 - 0.09 * step))
                    context.rectangle(x + (block - block * taper) / 2 + 1, top,
                                      max(1.5, block * taper - 2), tall - 2)
                    context.fill()
        else:
            context.set_source_rgba(*border, 0.30)
            context.rectangle(x, grate - 3, block, 3)
            context.fill()

    # The grate the whole thing stands on.
    context.set_source_rgba(*border, 0.95)
    context.rectangle(padding, grate, bar, 2)
    context.fill()

    if panel['mode'] == 'countdown':
        # The fire is laid and not lit. Every limit is already on screen -- the
        # marks, the numbers, the ceilings of all three sensor families -- so
        # what the machine is about to do is visible before it does it. The bar
        # drains a whole second at a time and unlocking is what cancels it,
        # which is the one thing that cannot be mistaken for a keystroke.
        seconds = panel['countdown'] if panel['countdown'] is not None else 0
        text(mono(f'{seconds}', 19000, accent, 700, 0)
             + mono('  SECONDS UNTIL THE BED WARMS', 7600, muted, 500, 2400),
             padding, hearth_top - 2, align='center')
        segments = 30
        step = bar / segments
        remaining = int(round(panel['countdown_left'] * segments))
        for index in range(segments):
            context.set_source_rgba(*(accent if index < remaining else border),
                                    0.85 if index < remaining else 0.35)
            context.rectangle(padding + index * step, hearth_top + 30,
                              max(2.0, step - 2), 3)
            context.fill()
    elif panel['mode'] == 'holding':
        text(mono('THE HEARTH IS COLD', 9500, muted, 500, 2200),
             padding, hearth_top + 8, align='center')

    # Row three: the scale, said in numbers under the marks it belongs to.
    labels_y = grate + 5
    text(mono(f'{panel["floor"]:.0f}°', 7200, muted, 500, 1000), padding, labels_y)
    for value, caption in ((panel['target'], 'TARGET'), (panel['ease'], 'EASE')):
        at = padding + bar * scale_position(panel, value)
        text(mono(f'{caption} {value:.0f}°', 7200, muted, 500, 1000),
             at - 44, labels_y, align='center', box=88)
    text(mono(f'STOP {panel["stop"]:.0f}°', 7200, alarm, 600, 1000),
         padding + bar + 8, labels_y, box=70)

    # Row four: every family that can stop this, with its own ceiling beside it.
    def reading(name, value, ceiling):
        if value is None:
            return mono(f'{name} UNREADABLE', 8200, alarm, 600)
        hot = value >= ceiling - 3.0
        return (mono(f'{name} ', 8200, muted, 500)
                + mono(f'{value:.0f}°', 8200, accent if hot else alarm, 600)
                + mono(f' / {ceiling:.0f}°', 8200, muted, 400))

    readout_y = grate + 22
    parts = [reading('CPU', panel['cpu'], panel['ease']),
             reading('BATTERY', panel['battery'], panel['battery_ceiling']),
             reading('SKIN', panel['skin'], panel['skin_ceiling'])]
    text(mono('   ·   ', 8200, border, 400).join(parts), padding, readout_y)
    lid = 'LID CLOSED · STRICT' if panel['regime'] == 'closed' else 'LID OPEN'
    text(mono(lid, 7600, muted, 500, 1800), padding, readout_y, align='right')

    # Row five: what this is on the left, why on the right, in their own halves
    # so neither can ever run into the other whatever the reason turns out say.
    footer_y = height - padding - 8
    left = int(inner * 0.42)
    right = inner - left
    text(mono(_headline(panel), 8000, accent, 600, 2400), padding, footer_y, box=left)
    text(mono(_notice(panel), 7200, muted, 400, 1200)
         + mono(f'  {GHOST_GLYPH}', 7200, accent, 400, 0),
         padding + left, footer_y, align='right', box=right)

    surface.flush()
    temporary = Path(str(target) + f'.{os.getpid()}.tmp')
    surface.write_to_png(str(temporary))
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    return target


# ---- publishing -------------------------------------------------------------


def read_state(runtime=None):
    """The state file we last wrote, as a plain mapping; empty when there is none."""
    try:
        text = state_path(runtime).read_text()
    except (OSError, RuntimeError):
        return {}
    found = {}
    for line in text.splitlines():
        key, _, value = line.partition(' ')
        if key and value:
            found[key] = value.strip()
    return found


def clear(runtime=None):
    """Take the panel off the lock screen. The images are left where they are.

    Removing the state file is the whole instruction: the locker sees no panel
    and draws its own indicator exactly as it did before this feature existed.
    A stamp going stale does the same thing a few seconds later, which is what
    covers this process being killed rather than exiting.
    """
    try:
        state_path(runtime).unlink(missing_ok=True)
        return True
    except (OSError, RuntimeError):
        return False


def publish(panel, palette, scale=2, runtime=None, now=None):
    """Render the hearth if it changed and point the locker at it.

    Returns the serial written, or None when there is nothing to show. The image
    is only redrawn when `content_key` moves, so a locked machine that is simply
    sitting there warm costs one `stat` on the locker's side and nothing here.
    """
    if panel is None:
        clear(runtime)
        return None
    directory = runtime_directory(runtime)
    previous = read_state(runtime)
    key = content_key(panel)
    try:
        serial = int(previous.get('serial', '0'))
    except ValueError:
        serial = 0
    image = previous.get('image') if previous.get('image') in IMAGE_NAMES else None

    if previous.get('key') != key or image is None:
        image = IMAGE_NAMES[1] if image == IMAGE_NAMES[0] else IMAGE_NAMES[0]
        render(panel, palette, scale, directory / image)
        serial += 1

    animated = bool(panel.get('animated'))
    lines = [
        'panel 1',
        f'serial {serial}',
        f'stamp {int(now if now is not None else time.time())}',
        f'stale {STALE_SECONDS}',
        f'image {image}',
        f'width {PANEL_WIDTH}',
        f'height {PANEL_HEIGHT}',
        f'gap {PANEL_GAP}',
        f'fade {MAINS_FADE_MS if animated else QUIET_FADE_MS}',
        f'poll {MAINS_POLL_MS if animated else QUIET_POLL_MS}',
        # The locker's own arc goes away while the hearth is up. It is the only
        # thing on the lock screen that counts keystrokes -- one highlight per
        # key, in a different colour for backspace -- and a panel that is
        # drawing the indicator area has no business leaving it there.
        'ring 0',
        # Above the clock, because the caption card owns the lower-left corner
        # and its height changes with the painting and the hour. The locker
        # puts it below instead if the indicator sits too near the top to fit.
        'place above',
        f'key {key}',
    ]
    path = state_path(runtime)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text('\n'.join(lines) + '\n')
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return serial
