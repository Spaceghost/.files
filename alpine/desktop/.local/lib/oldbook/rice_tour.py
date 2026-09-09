"""Keep a reading list of what was just added to the desktop, newest first.

The rice arrives faster than anyone remembers it. A feature lands, gets a
paragraph in RICE.md and a contract in FEATURES.md, and then waits for someone
to happen to read the right file. This is the desktop telling you itself: a
quiet card that names the newest things and how to set each one off.

Conky draws text and reports pointer events; it has no hover and no tooltip. So
the card carries exactly one description at a time -- the selected entry's --
and the pointer moves the selection. That is the whole trick: what a tooltip
would show on hover, this shows for the row the cursor is on, which makes the
description part of the card's fixed geometry instead of a floating surface
that would have to be a second Wayland client.

The list is deliberately data, not prose in a template. `rice.json` is the one
place an entry is written, and entries stay in file order within a date, so a
new feature goes at the top of the file and appears at the top of the card.
"""
import json
import os
from pathlib import Path
import re
import textwrap

# The last posture at which the card still carries its description block; the
# ladder in power_source decides, and an unregistered effect runs everywhere.
LADDER_EFFECT = 'rice-tour'
ROWS = 5
WIDTH = 50
IDENTIFIER = re.compile(r'[a-z0-9][a-z0-9-]{0,47}')
DATE = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
# What the pointer does, said on the card itself, because there is nowhere else
# a reader would think to look. The wheel turns a page where the compositor
# reports it; the page counter above says whether there is another page to go to.
LEGEND = 'Try ▸ {} · click next · right back · mid ✓'


def entries_path():
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'oldbook/rice.json'


def state_path():
    base = os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base) / 'oldbook/rice-state.json'


def load(path=None):
    """Read and check the list, newest first.

    Sorting is by date alone and Python's sort is stable, so entries added on
    the same day keep the order they were written in. That is the whole reason
    a new entry belongs at the top of the file rather than the bottom.
    """
    path = entries_path() if path is None else Path(path)
    document = json.loads(path.read_text())
    if document.get('version') != 1 or not isinstance(document.get('entries'), list):
        raise ValueError('Unsupported rice list: expected version 1 with an entries list')
    seen = set()
    entries = []
    for entry in document['entries']:
        entries.append(check(entry, seen))
    return sorted(entries, key=lambda item: item['date'], reverse=True)


def check(entry, seen=None):
    """Reject an entry the card could not draw or the Try link could not run."""
    seen = set() if seen is None else seen
    if not isinstance(entry, dict):
        raise ValueError('Every rice entry must be an object')
    identity = str(entry.get('id', ''))
    if not IDENTIFIER.fullmatch(identity):
        raise ValueError('Every rice entry needs a lowercase hyphenated id')
    if identity in seen:
        raise ValueError('Duplicate rice entry id: ' + identity)
    seen.add(identity)
    for key in ('title', 'summary', 'trigger'):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            raise ValueError(f'Rice entry {identity} needs a {key}')
    written = DATE.fullmatch(str(entry.get('date', '')))
    if not written:
        raise ValueError(f'Rice entry {identity} needs a YYYY-MM-DD date')
    if not 1 <= int(written.group(2)) <= 12 or not 1 <= int(written.group(3)) <= 31:
        raise ValueError(f'Rice entry {identity} has an impossible date')
    if 'detail' in entry and not isinstance(entry['detail'], str):
        raise ValueError(f'Rice entry {identity} detail must be text')
    run = entry.get('run')
    if run is not None and (not isinstance(run, list) or not run
                            or not all(isinstance(word, str) and word for word in run)):
        raise ValueError(f'Rice entry {identity} run must be a non-empty list of words')
    if 'terminal' in entry and not isinstance(entry['terminal'], bool):
        raise ValueError(f'Rice entry {identity} terminal must be true or false')
    return entry


def read_state(path=None):
    """The cursor and the ticks, forgiving of a state file that went missing."""
    try:
        record = json.loads((state_path() if path is None else Path(path)).read_text())
        cursor = int(record.get('cursor', 0))
        tried = [str(name) for name in record.get('tried', []) if isinstance(name, str)]
        return {'cursor': max(0, cursor), 'tried': tried}
    except (OSError, ValueError, TypeError, AttributeError):
        return {'cursor': 0, 'tried': []}


def write_state(state, path=None):
    path = state_path() if path is None else Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps({'cursor': int(state['cursor']),
                                     'tried': sorted(set(state['tried']))}, indent=2) + '\n')
    temporary.replace(path)


def move(cursor, total, step):
    """Step the selection, wrapping so the end of the list returns to the top."""
    if total <= 0:
        return 0
    return (cursor + step) % total


def page_move(cursor, total, step, rows=ROWS):
    """Step a whole page, landing on its first row rather than mid-page."""
    if total <= 0:
        return 0
    pages = max(1, -(-total // rows))
    return (((cursor // rows) + step) % pages) * rows


def clamp(cursor, total):
    return 0 if total <= 0 else min(max(0, cursor), total - 1)


def visible(entries, cursor, rows=ROWS):
    """The page the cursor is on, so the selection is always on screen."""
    start = (clamp(cursor, len(entries)) // rows) * rows
    return start, entries[start:start + rows]


def short_date(value):
    month, day = (int(part) for part in DATE.fullmatch(value).groups()[1:])
    return f'{day} {MONTHS[month - 1]}'


def escape(text):
    """Conky parses execpi output, so a stray $ in the data must stay literal."""
    return str(text).replace('$', '$$')


def fit(text, width):
    if width > 1 and len(text) > width:
        return text[:width - 1] + '…'
    return text[:width]


def panel_lines(entries, state, width=WIDTH, rows=ROWS, detailed=True):
    """The card body: the current page, then the selected entry's description.

    `detailed` is the battery's answer. With the description block shed the
    card is still a list of what is new, which is the part worth keeping on a
    critical battery; what goes is the block that changes on every click.
    """
    if not entries:
        return ['Nothing new to try; the list is empty.']
    cursor = clamp(state.get('cursor', 0), len(entries))
    tried = set(state.get('tried', ()))
    start, page = visible(entries, cursor, rows)
    lines = []
    for offset, entry in enumerate(page):
        selected = start + offset == cursor
        ticked = entry['id'] in tried
        colour = '${color1}▸ ' if selected else '${color}  '
        lines.append(colour + escape(fit(entry['title'], width - 4))
                     + ('${alignr}${color2}✓' if ticked else ''))
    # A short last page still holds the card open, so the description below it
    # never walks up the screen as the reader pages through.
    lines += [''] * (rows - len(page))
    if not detailed:
        return lines
    entry = entries[cursor]
    lines.append('${color2}${hr 1}')
    lines.append('${color}' + escape(fit(entry['title'], width - 8))
                 + '${alignr}${color2}' + escape(short_date(entry['date'])))
    # Always two lines, short summary or long: the card's height is fixed, and
    # a description that changed height would move the legend under the pointer.
    wrapped = textwrap.wrap(entry['summary'], width, max_lines=2, placeholder='…')
    for line in (wrapped + ['', ''])[:2]:
        lines.append('${color}' + escape(line))
    pages = max(1, -(-len(entries) // rows))
    counter = f'{cursor // rows + 1}/{pages}'
    lines.append('${color2}try  ' + escape(fit(entry['trigger'], width - len(counter) - 6))
                 + '${alignr}${color2}' + counter)
    lines.append('${color2}' + escape(fit(
        LEGEND.format('runs it' if entry.get('run') else 'says how'), width)))
    return lines


def panel(entries, state, width=WIDTH, rows=ROWS, detailed=True):
    return '\n'.join(panel_lines(entries, state, width, rows, detailed))


def listing(entries, state):
    """The same list for a terminal, where there is room for every trigger."""
    cursor = clamp(state.get('cursor', 0), len(entries))
    tried = set(state.get('tried', ()))
    lines = []
    for index, entry in enumerate(entries):
        marks = ('>' if index == cursor else ' ') + ('✓' if entry['id'] in tried else ' ')
        lines.append(f'{marks} {short_date(entry["date"]):>6}  {entry["title"]}')
        lines.append(f'      {entry["summary"]}')
        lines.append(f'      try: {entry["trigger"]}')
    return '\n'.join(lines)


def describe(entry):
    """One entry in full, for the terminal and for the Try notification."""
    parts = [entry['summary']]
    if entry.get('detail'):
        parts.append(entry['detail'])
    parts.append('Try: ' + entry['trigger'])
    return '\n'.join(parts)


def detailed_now(effect=LADDER_EFFECT):
    """Ask the shared power ladder whether the description block may be drawn."""
    try:
        import power_source
    except ImportError:
        return True
    return power_source.allows(effect)
