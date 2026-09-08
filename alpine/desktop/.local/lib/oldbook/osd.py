"""Display-independent state for the volume, brightness and keyboard-light pill.

The daemon only draws. This module decides what a datagram means, which glyph
and label a reading gets, and how the pill's opacity evolves, so the drawing
code samples ``alpha_at(now)`` on the compositor's frame clock and nothing
else keeps time. Times are monotonic milliseconds in the frame clock's scale.
"""
import json
import os
from pathlib import Path
import socket
import stat

KINDS = ('volume', 'mute', 'mic', 'mic-mute', 'brightness', 'keyboard')
# WirePlumber lets the sink be boosted to 150%; the bar clips at 100%.
MAX_VALUE = 150
MAX_MESSAGE = 512
HOLD_MS = 1100.0
FADE_MS = 260.0
FLASH_MS = 120.0
FLASH_ALPHA = 0.85

# The now-transmitting card: a slower, wider surface than the pill.
CARD_SLIDE_MS = 320.0
CARD_HOLD_MS = 4000.0
CARD_MAX_TEXT = 160
# A player that republishes the same metadata (a position tick, a volume
# change) must not re-announce the track it is already playing.
CARD_REPEAT_MS = 20000.0

# Nerd Font (Material Design) code points shared with the Waybar modules.
GLYPHS = {'volume-off': '\U000f0581', 'volume-low': '\U000f057f',
          'volume-medium': '\U000f0580', 'volume-high': '\U000f057e',
          'mic': '\U000f036c', 'mic-off': '\U000f036d',
          'brightness': '\U000f00df', 'keyboard': '\U000f0313'}


def endpoint(runtime=None):
    base = runtime or os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    return Path(base) / 'oldbook' / 'osd.sock'


def show_message(kind, value, muted=False):
    if kind not in KINDS:
        raise ValueError('Unknown feedback kind: ' + str(kind))
    value = max(0, min(MAX_VALUE, int(value)))
    return json.dumps({'action': 'show', 'kind': kind, 'value': value,
                       'muted': bool(muted)}).encode()


def flash_message():
    return json.dumps({'action': 'flash'}).encode()


def clean_text(value, limit=CARD_MAX_TEXT):
    """One tidy line from whatever a player publishes, or the empty string."""
    if isinstance(value, (list, tuple)):
        value = ', '.join(str(item) for item in value if item)
    if not isinstance(value, str):
        return ''
    value = ' '.join(value.split())
    return value[:limit]


def card_message(title, artist='', album='', art=''):
    title = clean_text(title)
    if not title:
        raise ValueError('a track card needs a title')
    return json.dumps({'action': 'card', 'title': title, 'artist': clean_text(artist),
                       'album': clean_text(album), 'art': clean_text(str(art), 1024)}).encode()


def track_identity(title, artist='', album=''):
    """What makes two announcements the same track, ignoring position ticks."""
    return (clean_text(title), clean_text(artist), clean_text(album))


def parse_message(data):
    """Return a validated request, or None for anything the pill must ignore."""
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_MESSAGE:
        return None
    try:
        payload = json.loads(bytes(data).decode())
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    action = payload.get('action')
    if action == 'flash':
        return {'action': 'flash'}
    if action == 'card':
        title = clean_text(payload.get('title'))
        if not title:
            return None
        art = payload.get('art')
        return {'action': 'card', 'title': title,
                'artist': clean_text(payload.get('artist')),
                'album': clean_text(payload.get('album')),
                'art': art if isinstance(art, str) else ''}
    if action != 'show':
        return None
    kind, value, muted = payload.get('kind'), payload.get('value'), payload.get('muted', False)
    if kind not in KINDS or not isinstance(muted, bool):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_VALUE:
        return None
    return {'action': 'show', 'kind': kind, 'value': value, 'muted': muted}


def describe(kind, value, muted=False):
    """Glyph, label and bar fill for one reading; kinds ending in -mute are toggles."""
    value = max(0, min(MAX_VALUE, int(value)))
    fill = min(1.0, value / 100.0)
    if kind in ('volume', 'mute'):
        if muted:
            glyph, label = GLYPHS['volume-off'], 'Muted'
        else:
            level = ('volume-low' if value <= 33 else
                     'volume-medium' if value <= 66 else 'volume-high')
            glyph, label = GLYPHS[level], 'Sound on' if kind == 'mute' else 'Volume'
    elif kind in ('mic', 'mic-mute'):
        if muted:
            glyph, label = GLYPHS['mic-off'], 'Microphone off'
        else:
            glyph, label = GLYPHS['mic'], 'Microphone on' if kind == 'mic-mute' else 'Microphone'
    elif kind == 'brightness':
        glyph, label = GLYPHS['brightness'], 'Brightness'
    elif kind == 'keyboard':
        glyph, label = GLYPHS['keyboard'], 'Keyboard light'
    else:
        raise ValueError('Unknown feedback kind: ' + str(kind))
    return {'glyph': glyph, 'label': label, 'value': value, 'fill': fill,
            'muted': bool(muted), 'boosted': value > 100}


class Feedback:
    """Opacity of the pill: fully visible while held, then a linear fade to zero.

    A linear fade settles exactly at zero with no overshoot, and a new reading
    during the fade snaps straight back to full opacity. With desktop
    animations disabled the pill simply disappears when the hold ends.
    """

    def __init__(self, hold_ms=HOLD_MS, fade_ms=FADE_MS, animate=True):
        if hold_ms < 0 or fade_ms <= 0:
            raise ValueError('hold must be nonnegative and fade positive')
        self.hold_ms, self.fade_ms, self.animate = float(hold_ms), float(fade_ms), animate
        self.shown_at = None
        self.content = None

    def show(self, content, now):
        self.content = content
        self.shown_at = float(now)

    def hide(self):
        self.shown_at = None
        self.content = None

    @property
    def visible(self):
        return self.shown_at is not None

    def fade_starts_at(self):
        return None if self.shown_at is None else self.shown_at + self.hold_ms

    def alpha_at(self, now):
        if self.shown_at is None:
            return 0.0
        elapsed = float(now) - self.shown_at
        if elapsed < self.hold_ms:
            return 1.0
        if not self.animate:
            return 0.0
        progress = (elapsed - self.hold_ms) / self.fade_ms
        return max(0.0, min(1.0, 1.0 - progress))

    def hidden_at(self, now):
        return self.alpha_at(now) <= 0.0


class Flash:
    """The screenshot wash: a bright frame that fades out over a few frames."""

    def __init__(self, started_at, duration_ms=FLASH_MS, peak=FLASH_ALPHA, animate=True):
        if duration_ms <= 0 or not 0.0 < peak <= 1.0:
            raise ValueError('flash needs a positive duration and a peak within (0, 1]')
        self.started_at, self.duration_ms, self.peak = float(started_at), float(duration_ms), peak
        self.animate = animate

    def alpha_at(self, now):
        if not self.animate:
            return 0.0
        progress = (float(now) - self.started_at) / self.duration_ms
        if progress < 0.0:
            return self.peak
        return max(0.0, self.peak * (1.0 - min(1.0, progress)))

    def finished_at(self, now):
        return self.alpha_at(now) <= 0.0


class Card:
    """The now-transmitting card: slide in, hold, slide out, then stop drawing.

    ``offset_at`` is how far off the right edge the card sits, in pixels, so
    the drawing code translates by it and nothing else keeps time. The slide
    eases out on the way in and in on the way out, settling exactly on 0 and
    on the full travel with no overshoot.
    """

    def __init__(self, content, started_at, travel, slide_ms=CARD_SLIDE_MS,
                 hold_ms=CARD_HOLD_MS, animate=True):
        if travel <= 0 or slide_ms <= 0 or hold_ms < 0:
            raise ValueError('a card needs positive travel, slide and a nonnegative hold')
        self.content = dict(content)
        self.started_at = float(started_at)
        self.travel = float(travel)
        self.slide_ms, self.hold_ms = float(slide_ms), float(hold_ms)
        self.animate = animate
        self.dismissed_at = None

    def dismiss(self, now):
        """Cut the hold short, from the current position, without a jump."""
        if self.dismissed_at is None:
            self.dismissed_at = max(float(now), self.started_at)

    def _leaves_at(self):
        entry = self.slide_ms if self.animate else 0.0
        natural = self.started_at + entry + self.hold_ms
        if self.dismissed_at is None:
            return natural
        return min(natural, self.dismissed_at)

    def offset_at(self, now):
        elapsed = float(now) - self.started_at
        if not self.animate:
            return 0.0 if float(now) < self._leaves_at() else self.travel
        if elapsed < self.slide_ms:
            # Cubic ease-out: quick departure, gentle arrival.
            progress = max(0.0, elapsed) / self.slide_ms
            return self.travel * (1.0 - progress) ** 3
        leaving = float(now) - self._leaves_at()
        if leaving <= 0.0:
            return 0.0
        # Cubic ease-in on the way out, mirroring the arrival.
        progress = min(1.0, leaving / self.slide_ms)
        return self.travel * progress ** 3

    def finished_at(self, now):
        return float(now) >= self._leaves_at() + (self.slide_ms if self.animate else 0.0)


class Announcer:
    """Decides whether a metadata change deserves a card.

    Players republish metadata for reasons that are not a new track, and the
    card must stay out of the way while the desktop is locked or the
    notification centre is open. Keeping the rule here means it is testable
    without a bus or a display.
    """

    def __init__(self, repeat_ms=CARD_REPEAT_MS):
        self.repeat_ms = float(repeat_ms)
        self.last_identity = None
        self.last_shown_at = None

    def consider(self, title, artist='', album='', now=0.0, playing=True,
                 enabled=True, locked=False, centre_open=False):
        identity = track_identity(title, artist, album)
        if not identity[0]:
            return False
        repeated = (identity == self.last_identity and self.last_shown_at is not None
                    and float(now) - self.last_shown_at < self.repeat_ms)
        # A suppressed announcement still counts as seen, so the card does not
        # ambush the user the moment they unlock or close the centre.
        self.last_identity = identity
        self.last_shown_at = float(now)
        return bool(enabled and playing and not locked and not centre_open and not repeated)


def send(payload, runtime=None):
    """Deliver one datagram to a running daemon; False means nobody is listening.

    Only an owned socket is used, so a stale path or another user's runtime
    can never receive the message, and the client never starts the daemon.
    """
    address = endpoint(runtime)
    try:
        info = os.stat(address, follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.settimeout(.2)
            client.sendto(payload, str(address))
        return True
    except OSError:
        return False
