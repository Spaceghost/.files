"""Tell a cat on the keyboard from a person at it, using evdev alone.

There is no cat sensor. There is a keyboard and a trackpad, and the two animals
use them in ways that do not overlap much:

    a person   presses one key at a time and lets it go in about a tenth of a
               second, holds at most three at once and only for an instant,
               and the keys they hold together are the ones a hand can reach.
    a cat      settles. Six or eight keys go down within a moment of each
               other and stay down for as long as she is comfortable, they are
               whatever was under the paw or the flank so they form a patch of
               the board rather than a chord, nothing is ever released cleanly,
               and the autorepeat runs until the buffer gives up.

So the discriminator is not one clever signal, it is a conjunction. Two
signals are mandatory and neither alone is enough:

    simultaneity  at least CROWD keys held down at the same moment
    persistence   that crowd held continuously for PERSISTENCE seconds

and at least one of four corroborating signals must agree:

    contiguity    the held keys form a connected patch of the board
    stillness     no clean short press-and-release anywhere in the recent past
    contact       the trackpad is reporting a contact far too large for a finger
    drumming      several distinct keys have gone into autorepeat

On top of that there is a veto that outranks everything: if the recent past
contains real typing -- several clean short press/release pairs -- the answer
is no, whatever else is true. A person resting a forearm across the keyboard
while thinking is the false positive this is built to refuse.

The posture is deliberately lopsided. Missing a cat costs a warm nap. A false
positive heats a laptop under someone's hands, so every threshold is set where
a person cannot plausibly reach it, and the caller adds one more gate on top:
nothing is reported present unless the session is locked.

The record is published as JSON under $XDG_RUNTIME_DIR/oldbook/, in the same
shape and with the same publish/read split as `power_source`, and carries a
`last_seen` wall-clock stamp so anything can ask the thirty-second question
without talking to the daemon.
"""
import json
import os
from pathlib import Path
import struct
import time

# struct input_event on 64-bit Linux: timeval, type, code, value.
EVENT = struct.Struct('@llHHI')
EVENT_SIZE = EVENT.size
EV_KEY = 0x01
EV_ABS = 0x03
KEY_UP, KEY_DOWN, KEY_REPEAT = 0, 1, 2
ABS_MT_TOUCH_MAJOR = 0x30
ABS_TOOL_WIDTH = 0x1c

# How many keys must be down together. A person's largest real chord is four
# (Ctrl+Alt+Shift+key) and it lasts an instant; five held keys is already
# outside what hands do on purpose.
CROWD = 5
# ...and for how long, continuously. Two seconds is twenty times a keystroke.
PERSISTENCE = 2.0
# A connected patch of this many keys is a paw or a flank, not a reach.
CONTIGUOUS = 4
# A press and release shorter than this is a keystroke; longer is a rest.
TYPING_HOLD = 0.25
# Recent past for the corroborating stillness signal and for the veto.
TYPING_WINDOW = 5.0
VETO_WINDOW = 10.0
VETO_KEYSTROKES = 3
# Trackpad contact as a fraction of the device's own maximum. A fingertip on
# bcm5974 sits near a tenth of full scale; this is far above a thumb.
CONTACT_FRACTION = 0.45
CONTACT_WINDOW = 3.0
# Distinct keys in autorepeat before that counts as corroboration.
DRUMMING_KEYS = 3
# How long a sitting survives a quiet moment before she is called gone. A cat
# shifts her weight; the keys change but she has not left.
LINGER = 8.0
# The question the lid asks: was she here within the last half minute?
RECENT = 30.0

# The physical board, row by row, as evdev names. Column position is
# normalised across rows so that a key in the middle of the number row is
# adjacent to the one in the middle of the row below it, which is the whole
# point: rows have different lengths and raw indices would not line up.
ROWS = (
    ('ESC', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'),
    ('GRAVE', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'MINUS', 'EQUAL', 'BACKSPACE'),
    ('TAB', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', 'LEFTBRACE', 'RIGHTBRACE',
     'BACKSLASH'),
    ('CAPSLOCK', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'SEMICOLON', 'APOSTROPHE', 'ENTER'),
    ('LEFTSHIFT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', 'COMMA', 'DOT', 'SLASH', 'RIGHTSHIFT'),
    ('FN', 'LEFTCTRL', 'LEFTALT', 'LEFTMETA', 'SPACE', 'RIGHTMETA', 'RIGHTALT',
     'LEFT', 'DOWN', 'UP', 'RIGHT'),
)
KEY_CODES = {
    'ESC': 1, '1': 2, '2': 3, '3': 4, '4': 5, '5': 6, '6': 7, '7': 8, '8': 9, '9': 10,
    '0': 11, 'MINUS': 12, 'EQUAL': 13, 'BACKSPACE': 14, 'TAB': 15, 'Q': 16, 'W': 17,
    'E': 18, 'R': 19, 'T': 20, 'Y': 21, 'U': 22, 'I': 23, 'O': 24, 'P': 25,
    'LEFTBRACE': 26, 'RIGHTBRACE': 27, 'ENTER': 28, 'LEFTCTRL': 29, 'A': 30, 'S': 31,
    'D': 32, 'F': 33, 'G': 34, 'H': 35, 'J': 36, 'K': 37, 'L': 38, 'SEMICOLON': 39,
    'APOSTROPHE': 40, 'GRAVE': 41, 'LEFTSHIFT': 42, 'BACKSLASH': 43, 'Z': 44, 'X': 45,
    'C': 46, 'V': 47, 'B': 48, 'N': 49, 'M': 50, 'COMMA': 51, 'DOT': 52, 'SLASH': 53,
    'RIGHTSHIFT': 54, 'LEFTALT': 56, 'SPACE': 57, 'CAPSLOCK': 58, 'F1': 59, 'F2': 60,
    'F3': 61, 'F4': 62, 'F5': 63, 'F6': 64, 'F7': 65, 'F8': 66, 'F9': 67, 'F10': 68,
    'F11': 87, 'F12': 88, 'RIGHTCTRL': 97, 'RIGHTALT': 100, 'UP': 103, 'LEFT': 105,
    'RIGHT': 106, 'DOWN': 108, 'LEFTMETA': 125, 'RIGHTMETA': 126, 'FN': 464,
}
# A row is stretched onto this many units wide, so columns compare across rows.
ROW_SPAN = 13.0
# Keys within this much of each other horizontally, on the same or the next
# row, are touching. One unit is one key width on the longest row.
NEIGHBOUR = 1.6


def _grid():
    positions = {}
    for row, names in enumerate(ROWS):
        step = ROW_SPAN / max(1, len(names) - 1)
        for column, name in enumerate(names):
            code = KEY_CODES.get(name)
            if code is not None:
                positions[code] = (row, column * step)
    return positions


GRID = _grid()


def adjacent(first, second):
    """Do these two key codes touch on the board?"""
    left, right = GRID.get(first), GRID.get(second)
    if left is None or right is None:
        return False
    return abs(left[0] - right[0]) <= 1 and abs(left[1] - right[1]) <= NEIGHBOUR


def largest_patch(codes):
    """The size of the biggest connected group among these held keys."""
    remaining = {code for code in codes if code in GRID}
    biggest = 0
    while remaining:
        seed = remaining.pop()
        group, frontier = {seed}, [seed]
        while frontier:
            current = frontier.pop()
            touching = {code for code in remaining if adjacent(current, code)}
            remaining -= touching
            group |= touching
            frontier.extend(touching)
        biggest = max(biggest, len(group))
    return biggest


class Presence:
    """The running judgement, fed one evdev event at a time.

    Deliberately pure: it holds no file descriptors and reads no clock of its
    own, so the whole discriminator can be driven from a list of events in a
    test at whatever timestamps the test likes.
    """

    def __init__(self, contact_maximum=None):
        self.contact_maximum = contact_maximum
        self.held = {}
        self.crowd_since = None
        self.repeating = set()
        self.keystrokes = []
        self.contact_at = None
        self.seen_at = None
        self.sitting_since = None

    # ---- intake ------------------------------------------------------------

    def key(self, now, code, value):
        if value == KEY_DOWN:
            self.held.setdefault(code, now)
        elif value == KEY_REPEAT:
            if code in self.held:
                self.repeating.add(code)
        elif value == KEY_UP:
            pressed = self.held.pop(code, None)
            self.repeating.discard(code)
            if pressed is not None and now - pressed <= TYPING_HOLD:
                self.keystrokes.append(now)
        if len(self.held) >= CROWD:
            if self.crowd_since is None:
                self.crowd_since = now
        else:
            self.crowd_since = None
            if not self.held:
                self.repeating.clear()

    def contact(self, now, value):
        """A trackpad contact size, raw; large enough is remembered as recent."""
        if self.contact_maximum:
            fraction = value / float(self.contact_maximum)
        else:
            return
        if fraction >= CONTACT_FRACTION:
            self.contact_at = now

    def event(self, now, kind, code, value):
        if kind == EV_KEY and code in GRID:
            self.key(now, code, value)
        elif kind == EV_ABS and code in (ABS_MT_TOUCH_MAJOR, ABS_TOOL_WIDTH) and value > 0:
            self.contact(now, value)

    def feed(self, now, data):
        """Decode a read() from an evdev device. Partial trailing bytes are dropped."""
        for offset in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            _sec, _usec, kind, code, value = EVENT.unpack_from(data, offset)
            self.event(now, kind, code, value)

    # ---- judgement ---------------------------------------------------------

    def keystrokes_since(self, now, window):
        """How many real keystrokes landed in the last `window` seconds.

        Two windows ask this, and the long one is the veto, so the history is
        only ever pruned to the longest of them. Pruning to whichever window
        asked first would have let the five-second stillness check quietly
        delete the evidence the ten-second veto depends on.
        """
        while self.keystrokes and self.keystrokes[0] < now - max(TYPING_WINDOW, VETO_WINDOW):
            self.keystrokes.pop(0)
        cutoff = now - window
        return sum(1 for stamp in self.keystrokes if stamp >= cutoff)

    def signals(self, now):
        held = set(self.held)
        found = {}
        found['simultaneity'] = len(held) >= CROWD
        found['persistence'] = (self.crowd_since is not None
                                and now - self.crowd_since >= PERSISTENCE)
        found['contiguity'] = largest_patch(held) >= CONTIGUOUS
        found['stillness'] = self.keystrokes_since(now, TYPING_WINDOW) == 0
        found['contact'] = (self.contact_at is not None
                            and now - self.contact_at <= CONTACT_WINDOW)
        found['drumming'] = len(self.repeating) >= DRUMMING_KEYS
        return found

    def vetoed(self, now):
        """Real typing in the recent past refuses the whole judgement."""
        return self.keystrokes_since(now, VETO_WINDOW) >= VETO_KEYSTROKES

    def judge(self, now):
        """Decide, remember the sitting, and return the evidence.

        The linger is why this mutates: a cat shifting her weight momentarily
        drops below the crowd, and treating that as her leaving would make the
        thirty-second lid question flap several times a minute.
        """
        found = self.signals(now)
        veto = self.vetoed(now)
        corroboration = sorted(name for name in
                               ('contiguity', 'stillness', 'contact', 'drumming')
                               if found[name])
        decided = (not veto and found['simultaneity'] and found['persistence']
                   and bool(corroboration))
        if decided:
            if self.sitting_since is None:
                self.sitting_since = now - PERSISTENCE
            self.seen_at = now
        present = decided or (self.seen_at is not None and now - self.seen_at <= LINGER)
        if not present:
            self.sitting_since = None
        confidence = 0.0
        if decided:
            confidence = min(0.95, 0.6 + 0.1 * len(corroboration))
        return {'present': present, 'deciding': decided, 'vetoed': veto,
                'confidence': round(confidence, 2), 'keys_down': len(self.held),
                'patch': largest_patch(set(self.held)),
                'signals': sorted(name for name, value in found.items() if value),
                'corroboration': corroboration,
                'since': self.sitting_since, 'seen_at': self.seen_at}


# ---- the published record --------------------------------------------------


def state_path(runtime=None):
    runtime = runtime or os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise RuntimeError('XDG_RUNTIME_DIR is required to publish the cat record')
    directory = Path(runtime) / 'oldbook'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory / 'cat.json'


def publish(record, runtime=None):
    path = state_path(runtime)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)


def published(runtime=None):
    """The daemon's record, or an honest empty one when nothing is running."""
    try:
        return json.loads(state_path(runtime).read_text())
    except (OSError, ValueError, RuntimeError):
        return {'present': False, 'last_seen': None, 'running': False}


def seen_within(seconds=RECENT, record=None, now=None):
    """Was a cat on the keyboard within this many seconds?

    Wall clock, because the answer has to survive the reader being a different
    process from the writer. A record from before the last boot cannot pass:
    `last_seen` in the future or absurdly far in the past both read as no.
    """
    record = published() if record is None else record
    stamp = record.get('last_seen')
    now = time.time() if now is None else now
    try:
        elapsed = now - float(stamp)
    except (TypeError, ValueError):
        return False
    return 0 <= elapsed <= seconds
