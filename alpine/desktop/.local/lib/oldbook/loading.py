"""One loading language for every Oldbook helper that makes you wait.

Before this each long-running helper invented its own waiting noise, or made
none at all: `package-archive` counted every fiftieth APK into stdout,
`remote-build` printed one line and then went quiet for the length of a
compile, and `check-features --run` let seventeen unittest processes talk over
each other with no sense of how far in you were. The desktop already speaks one
visual language everywhere else; the terminal should too.

The vocabulary is three words and no more. A segmented bar for work whose total
is known before it starts, a stepped spinner for work whose total is not, and a
list of phases where each finished phase keeps its line and its result mark.
All three are built from the roles `overlay_theme.read_palette` already
publishes, so a new theme recolours the terminal without touching this file.

Two rules run through all of it, and they are the same rule twice. **Nothing
here moves on its own.** There is no timer, no thread and no frame clock: a
line is repainted because the caller reported work, so when the work stops the
drawing stops in the same instant, with nothing left breathing on the screen.
And **a frame is a courtesy, not information** — repaints are capped at ten a
second, an unchanged line is never rewritten, and everything the terminal
cannot show (a pipe, `NO_COLOR`, a dumb terminal, a machine running off its
battery) degrades to plain stepped lines carrying exactly the same events.
"""
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

import overlay_theme
import power_source

# The power ladder entry this module asks about. Live repainting is eyecandy;
# the events it decorates are not, and they still print on a flat battery.
EFFECT = 'terminal-progress'
# Ten repaints a second is well under a display frame and far above the rate a
# reader can follow, so nothing is gained by drawing faster and a busy loop
# would pay for it in wakeups.
MIN_INTERVAL = 0.1
# In a log there is no line to repaint, so progress is emitted as whole lines
# and only for work slow enough that somebody is waiting on it.
PLAIN_INTERVAL = 2.0
BAR_WIDTH = 24
# Below this a terminal is not reporting a narrow window, it is reporting that
# it does not know: a pty with no winsize answers zero columns, and trimming
# every label to fit zero columns would erase the whole language.
MIN_WIDTH = 20
INDENT = '  '
RESET = '\033[0m'

# Discrete on purpose. A filled segment either landed or it did not, and the
# spinner steps between four positions rather than sweeping between them.
SEGMENTS = ('▰', '▱')
SPINNER = ('▖', '▘', '▝', '▗')
ELLIPSIS = '…'
ASCII_SEGMENTS = ('#', '-')
ASCII_SPINNER = ('|', '/', '-', '\\')
ASCII_ELLIPSIS = '...'

# The marks `oldbook-rebuild` has always used, so the desktop keeps one
# alphabet for "did it work" whichever helper is doing the talking.
MARKS = {'done': '+', 'failed': 'x', 'skipped': '=', 'blocked': '!'}
# Which palette colour each part of the language paints with. Success and
# failure want two named colours the shared roles do not carry; a theme that
# declares them lends them, and one that does not falls back to a role rather
# than to a shade chosen by eye.
ROLES = {'done': 'green', 'failed': 'red', 'skipped': 'muted', 'blocked': 'accent',
         'working': 'accent', 'filled': 'accent', 'empty': 'muted',
         'label': 'foreground', 'note': 'muted', 'count': 'muted'}
NAMED = ('green', 'red')
# Terminals with a palette of their own that 24-bit SGR would talk past: the
# boot console paints from the kernel's sixteen colours and `dumb` has none.
UNCOLOURED = ('dumb', 'linux')


def declared(directory=None):
    """The named colours the active theme declares, beyond the shared roles.

    `read_palette` answers the question every overlay asks and drops the rest
    of the descriptor, but a result mark wants the theme's own green and red.
    Reading them here keeps the loading language inside the palette the theme
    owns; any problem at all simply leaves the roles to stand in.
    """
    directory = overlay_theme.THEMES if directory is None else directory
    try:
        identity = Path(directory, 'current').read_text().strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', identity):
            return {}
        source = json.loads(Path(directory, identity + '.json').read_text())['palette']
        return {name: source[name].lower() for name in NAMED
                if isinstance(source.get(name), str) and overlay_theme.HEX.fullmatch(source[name])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def theme_colours(directory=None):
    """Every colour the loading language paints with, from the active theme."""
    palette = dict(overlay_theme.read_palette(
        overlay_theme.THEMES if directory is None else directory))
    palette.setdefault('green', palette['accent'])
    palette.setdefault('red', palette['foreground'])
    palette.update(declared(directory))
    return palette


def sgr(value):
    """A 24-bit foreground escape for one #rrggbb theme colour."""
    red, green, blue = (int(value[index:index + 2], 16) for index in (1, 3, 5))
    return f'\033[38;2;{red};{green};{blue}m'


class Style:
    """Colour for one role of the language, or nothing at all.

    Kept separate from the renderers so every line can be produced as plain
    text and compared as a string, which is how the tests read them.
    """

    def __init__(self, colours=None):
        self.colours = dict(colours or {})

    def __call__(self, role, text):
        code = self.colours.get(role)
        return f'{code}{text}{RESET}' if code and text else text

    def __bool__(self):
        return bool(self.colours)


PLAIN = Style()


def theme_style(palette=None, directory=None):
    palette = theme_colours(directory) if palette is None else palette
    return Style({role: sgr(palette[name]) for role, name in ROLES.items() if name in palette})


def render_bar(done, total, width=BAR_WIDTH, segments=SEGMENTS, style=PLAIN):
    """Filled segments then empty ones; full only when the work is actually done."""
    if width < 1:
        raise ValueError('a bar needs at least one segment')
    done = max(0, min(int(done), int(total)))
    filled = width if total and done >= total else (int(done * width // total) if total > 0 else 0)
    return (style('filled', segments[0] * filled)
            + style('empty', segments[1] * (width - filled)))


def spinner_frame(step, frames=SPINNER):
    """The glyph for one reported step. Steps, never seconds: see the module note."""
    return frames[int(step) % len(frames)]


def fit(text, room, ellipsis=ELLIPSIS):
    """Trim a caller's text to the room left on the line."""
    if room <= 0:
        return ''
    if len(text) <= room:
        return text
    return text[:room - len(ellipsis)] + ellipsis if room > len(ellipsis) else text[:room]


def _compose(prefix, plain_prefix, label, note, width, style, ellipsis):
    """Assemble a line, dropping the note and then trimming the label to fit."""
    label = '' if label is None else str(label)
    room = None if width is None else max(0, width - len(plain_prefix))
    if note and room is not None and len(label) + 2 + len(note) > room:
        note = None
    if room is not None:
        label = fit(label, room if not note else max(0, room - 2 - len(note)), ellipsis)
    line = prefix + style('label', label)
    if note:
        line += '  ' + style('note', note)
    return line


def render_step(state, label, note=None, index=None, total=None, frame=0, width=None,
                style=PLAIN, spinner=SPINNER, ellipsis=ELLIPSIS, indent=INDENT):
    """One phase's line: its mark, an optional counter, its name, an optional note.

    A finished phase keeps this line for good, which is the whole point of the
    step list: the terminal ends up holding the record of what happened rather
    than one bar that erased its own history.
    """
    mark = spinner_frame(frame, spinner) if state == 'working' else MARKS[state]
    count = f'[{index}/{total}] ' if index is not None and total else ''
    plain = f'{indent}{mark} {count}'
    prefix = indent + style(state, mark) + ' ' + style('count', count)
    return _compose(prefix, plain, label, note, width, style, ellipsis)


def render_progress(label, done, total, note=None, width=None, style=PLAIN,
                    bar_width=BAR_WIDTH, segments=SEGMENTS, ellipsis=ELLIPSIS,
                    indent=INDENT):
    """A bar, the count behind it, and what the work is called."""
    count = f'{max(0, min(int(done), int(total)))}/{int(total)}'
    plain = f'{indent}{segments[0] * bar_width}  {count}  '
    prefix = (indent + render_bar(done, total, bar_width, segments, style)
              + '  ' + style('count', count) + '  ')
    return _compose(prefix, plain, label, note, width, style, ellipsis)


class Terminal:
    """What the stream in front of us can actually do, decided once.

    Everything expensive or environmental is answered here and then never asked
    again: the power posture is one sysfs walk, the palette is one file read,
    and neither belongs inside a repaint. Every answer can be supplied by the
    caller instead, which is how the tests drive a live terminal without one.
    """

    def __init__(self, stream=None, live=None, colour=None, width=None, palette=None,
                 environ=None, allows=None):
        self.stream = sys.stderr if stream is None else stream
        environ = os.environ if environ is None else environ
        mode = environ.get('OLDBOOK_LOADING', 'auto')
        term = environ.get('TERM', '')
        tty = False
        try:
            tty = bool(self.stream.isatty())
        except (AttributeError, ValueError, OSError):
            tty = False
        self.tty = tty
        allows = power_source.allows if allows is None else allows
        if live is None:
            live = tty and term != 'dumb' and bool(allows(EFFECT))
        self.live = {'plain': False, 'live': True}.get(mode, bool(live))
        if colour is None:
            # no-color.org: set *and not empty*. An exported-but-blank variable
            # is a shell accident rather than a preference.
            colour = tty and term not in UNCOLOURED and not environ.get('NO_COLOR')
        self.colour = bool(colour) and mode != 'plain'
        self.style = theme_style(palette) if self.colour else PLAIN
        self.width = self.measure() if width is None else width
        encoding = (getattr(self.stream, 'encoding', '') or '').lower()
        wide = 'utf' in encoding or 'utf' in environ.get('LANG', '').lower()
        self.segments = SEGMENTS if wide else ASCII_SEGMENTS
        self.spinner = SPINNER if wide else ASCII_SPINNER
        self.ellipsis = ELLIPSIS if wide else ASCII_ELLIPSIS

    def measure(self):
        """Columns of the stream we actually draw on, not of stdout.

        Progress usually goes to stderr while the work talks on stdout, and
        `shutil.get_terminal_size` asks stdout; a piped stdout would otherwise
        pin every line to eighty columns on a wide terminal.
        """
        for probe in (lambda: os.get_terminal_size(self.stream.fileno()).columns,
                      lambda: shutil.get_terminal_size((80, 24)).columns):
            try:
                columns = probe()
            except (OSError, AttributeError, ValueError):
                continue
            if columns >= MIN_WIDTH:
                return columns
        return 80

    def write(self, text):
        """A helper's progress must never be the reason its work fails."""
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            self.live = False


class _Line:
    """The one line a live indicator owns, and the budget it repaints under."""

    def __init__(self, terminal, interval=MIN_INTERVAL, clock=time.monotonic):
        self.terminal = terminal
        self.interval = interval
        self.clock = clock
        self.drawn = None
        self.at = None

    def paint(self, text, force=False):
        """Repaint, unless it would be too soon or would change nothing."""
        if not self.terminal.live or text == self.drawn:
            return False
        now = self.clock()
        if not force and self.at is not None and now - self.at < self.interval:
            return False
        self.terminal.write('\r\033[2K' + text)
        self.drawn, self.at = text, now
        return True

    def commit(self, text):
        """Leave one line on the terminal for good and release the live line."""
        if self.terminal.live and self.drawn == text:
            self.terminal.write('\n')          # already on screen; only end it
        else:
            erase = '\r\033[2K' if self.terminal.live and self.drawn is not None else ''
            self.terminal.write(erase + text + '\n')
        self.drawn, self.at = None, None

    def clear(self):
        if self.terminal.live and self.drawn is not None:
            self.terminal.write('\r\033[2K')
        self.drawn = None


class Progress:
    """A segmented bar for work whose total is known before it starts.

    The bar is redrawn when a segment could have moved and never more than ten
    times a second. Off a live terminal it stops being a bar and becomes a
    handful of plain lines, emitted only while the work is slow enough that
    somebody is waiting on it: a job that finishes before the first line is due
    leaves nothing in the log at all.
    """

    def __init__(self, label, total, terminal=None, width=BAR_WIDTH, clock=time.monotonic):
        self.terminal = Terminal() if terminal is None else terminal
        self.label = label
        self.total = max(0, int(total))
        self.width = width
        self.clock = clock
        self.done = 0
        self.note = None
        self.line = _Line(self.terminal, clock=clock)
        self._started = clock()
        self._emitted = 0
        self._plain_at = None
        self._plain_lines = 0

    def render(self, done=None, note=None):
        return render_progress(self.label, self.done if done is None else done, self.total,
                               note=self.note if note is None else note,
                               width=self.terminal.width, style=self.terminal.style,
                               bar_width=self.width, segments=self.terminal.segments,
                               ellipsis=self.terminal.ellipsis)

    def update(self, done, note=None):
        self.done = max(0, min(int(done), self.total))
        if note is not None:
            self.note = note
        self._show()
        return self.done

    def advance(self, count=1, note=None):
        return self.update(self.done + count, note)

    def _segments_filled(self):
        if self.total <= 0:
            return 0
        return self.width if self.done >= self.total else int(self.done * self.width // self.total)

    def _show(self, force=False):
        if self.terminal.live:
            self.line.paint(self.render(), force=force)
            return
        # A run that never had anything to say leaves nothing behind: the final
        # line is a summary of lines already printed, not an announcement.
        if force and not self._plain_lines:
            return
        filled = self._segments_filled()
        now = self.clock()
        since = now - (self._started if self._plain_at is None else self._plain_at)
        if not force and (filled == self._emitted or since < PLAIN_INTERVAL):
            return
        self.line.commit(self.render())
        self._emitted, self._plain_at = filled, now
        self._plain_lines += 1

    def finish(self, note=None):
        """Settle exactly on the total; a bar that stops at 23/24 reads as a fault."""
        self.done = self.total
        if note is not None:
            self.note = note
        if self.terminal.live:
            self.line.commit(self.render())
        else:
            self._show(force=True)

    def __enter__(self):
        self._show(force=self.terminal.live)
        return self

    def __exit__(self, kind, value, trace):
        if kind is None:
            self.finish()
        else:
            self.line.clear()
        return False


class Spinner:
    """A stepped mark for work with no total, advanced by the caller.

    It moves one glyph per reported step and not otherwise. That is the whole
    design: an indicator that spins on a timer is ambient motion, and ambient
    motion is exactly what this desktop does not do. A long silent wait shows a
    still glyph beside the name of what is being waited on, which is honest.
    """

    def __init__(self, label, terminal=None, clock=time.monotonic):
        self.terminal = Terminal() if terminal is None else terminal
        self.label = label
        self.clock = clock
        self.count = 0
        self.note = None
        self.line = _Line(self.terminal, clock=clock)

    def render(self, state='working', label=None, note=None):
        return render_step(state, self.label if label is None else label,
                           note=self.note if note is None else note, frame=self.count,
                           width=self.terminal.width, style=self.terminal.style,
                           spinner=self.terminal.spinner, ellipsis=self.terminal.ellipsis)

    def step(self, note=None):
        self.count += 1
        if note is not None:
            self.note = note
        self.line.paint(self.render())
        return self.count

    def finish(self, state='done', label=None, note=None):
        if note is not None:
            self.note = note
        self.line.commit(self.render(state, label))

    def __enter__(self):
        self.line.paint(self.render(), force=True)
        return self

    def __exit__(self, kind, value, trace):
        self.finish('done' if kind is None else 'failed')
        return False


class StepList:
    """Multi-phase work where every finished phase keeps its line and its mark.

    The phase in hand is drawn on the live line and replaced in place by its
    result, so the scrollback a run leaves behind is exactly the list of things
    that happened — the same list a pipe or a log would have received, with no
    escape codes and no erased frames in between.

    A phase whose own work prints (a compiler, a test runner) is declared
    ``quiet=False``. It gets no live line, because it would be overwritten the
    moment the work opened its mouth; only its result line is printed.
    """

    def __init__(self, terminal=None, total=None, indent=INDENT, clock=time.monotonic):
        self.terminal = Terminal() if terminal is None else terminal
        self.total = total
        self.indent = indent
        self.index = 0
        self.label = None
        self.note = None
        self.count = 0
        self.quiet = True
        self.results = []
        self.line = _Line(self.terminal, clock=clock)

    def render(self, state='working', label=None, note=None):
        return render_step(state, self.label if label is None else label,
                           note=self.note if note is None else note,
                           index=self.index or None, total=self.total, frame=self.count,
                           width=self.terminal.width, style=self.terminal.style,
                           spinner=self.terminal.spinner, ellipsis=self.terminal.ellipsis,
                           indent=self.indent)

    def start(self, label, quiet=True, note=None):
        self.index += 1
        self.label, self.note, self.count, self.quiet = label, note, 0, quiet
        if quiet:
            self.line.paint(self.render(), force=True)
        return self

    def tick(self, note=None):
        """Advance the working mark one step, for a phase reporting sub-progress."""
        self.count += 1
        if note is not None:
            self.note = note
        if self.quiet:
            self.line.paint(self.render())
        return self.count

    def finish(self, state='done', label=None, note=None):
        self.results.append(state)
        self.line.commit(self.render(state, label, note))
        self.label = self.note = None
        return state

    def mark(self, state, label, note=None):
        """A phase that is already over: one completed line, no live line at all."""
        self.index += 1
        self.label, self.note, self.count, self.quiet = label, note, 0, True
        return self.finish(state)

    @contextlib.contextmanager
    def step(self, label, quiet=True, note=None):
        """Run one phase, marking it failed and re-raising if it goes wrong."""
        self.start(label, quiet=quiet, note=note)
        try:
            yield self
        except BaseException:
            self.finish('failed')
            raise
        self.finish()

    def failures(self):
        return self.results.count('failed')
