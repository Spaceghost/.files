"""A discrete glyph naming what a captioned Claude or Codex window is doing.

The strip already shows a window's title; this adds one more segment, in the
same stepped-glyph vocabulary `loading.py` speaks everywhere else in this
desktop, so an agent window's caption says whether it is waiting on Jack
without borrowing a spinner that turns on a clock. Nothing here redraws on a
timer of its own -- a caller polls at whatever interval it chooses and only
repaints when the glyph this module returns has actually changed, the same
rule `carousel_view.py`'s theme-drift check already follows.

Two independent, honest signals, not one invented one:

* `oldbook-claude-notify` and `oldbook-codex-notify` both write a routing
  record to `$XDG_RUNTIME_DIR/oldbook/<claude|codex>-events/<hash>.json`
  exactly when that session is waiting on a permission or Jack's attention,
  and delete it the moment the wait ends. A live, unexpired record matching
  this window's tty or tmux pane is read as "waiting on you" -- the one state
  this desktop already promises is real, because the record's own producer
  is the thing that just stopped to ask.
* Codex additionally names its own run state in its window title
  (`app_identity._codex_state`, already parsed into `identity['state']` by
  `ApplicationResolver`). When that is present and nothing is waiting, it
  reads as "working" -- Codex said so itself, in its own words.

Claude Code embeds no equivalent run-state string, so a Claude window that is
not waiting shows no glyph at all rather than a guess dressed as a fact.
"""
import json
from pathlib import Path

import loading

# The one glyph this module invents: everything else is read from a producer
# that already knows what it means. Blocked, in loading.py's own alphabet, is
# exactly this -- work that has stopped and is waiting to be let through.
WAITING = loading.MARKS['blocked']
# A single, unmoving frame from the stepped spinner: presence, not motion.
# Only ever this one frame, because nothing here advances it on a clock --
# advancing it would need a reported step this data does not have.
WORKING = loading.SPINNER[0]

WAITING_EVENTS = frozenset(('attention', 'permission-requested'))


def load_records(root, now):
    """Every unexpired routing record under one events directory.

    Corrupt or foreign-shaped files are skipped rather than raised on: this
    reads a directory another process writes to continuously, and a half
    -written file mid-rename is an expected transient, not a bug to surface
    in a window caption.
    """
    root = Path(root)
    records = []
    try:
        paths = sorted(root.glob('*.json'))
    except OSError:
        return records
    for path in paths:
        try:
            document = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(document, dict):
            continue
        valid_until = document.get('valid_until')
        if isinstance(valid_until, (int, float)) and not isinstance(valid_until, bool) \
                and valid_until < now:
            continue
        records.append(document)
    return records


def matches(identity, record):
    """The same tty-first, then-pane rule oldbook-notification-led already
    uses to route one live window to one waiting session."""
    tty = identity.get('tty')
    if tty:
        return record.get('tty') == tty
    pane = identity.get('tmux_pane')
    if pane:
        return record.get('tmux_pane') == pane
    return False


def waiting(identity, records):
    return any(matches(identity, record) and record.get('event') in WAITING_EVENTS
              for record in records)


def glyph(identity, records):
    """None, or the one glyph naming this window's agent state right now.

    ``identity`` is one window's resolved shape from
    ``app_identity.ApplicationResolver`` -- at least ``kind``, and whichever
    of ``tty``/``tmux_pane``/``state`` it carries. ``records`` is every
    unexpired routing record for this identity's ``kind`` (Claude records for
    a Claude window, Codex records for a Codex window) -- the caller reads
    the one directory that applies rather than this function reading both.
    """
    kind = identity.get('kind')
    if kind not in ('claude', 'codex'):
        return None
    if waiting(identity, records):
        return WAITING
    if kind == 'codex' and identity.get('state'):
        return WORKING
    return None
