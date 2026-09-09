"""The set of ways the desktop can answer a cat, and which one is chosen.

She sits on the keyboard while the machine is locked; what happens next should
be a list the user picks from rather than one behaviour welded into the
detector. So this is a registry with exactly the shape of the rice list in
`rice.json` -- version, an entries array, one object per entry with an id, a
title, a date and a couple of lines of prose -- because that shape has already
proved that adding a thing to this desktop should be adding a line of data.

An entry names a `handler`. Exactly one handler exists today, `bed`, and it is
the selected one: the machine deliberately runs warm for her. An entry whose
handler is not implemented is still a legal, listable, selectable entry; it
simply does nothing when it comes round, and says so. That is the point of
writing it this way now: the second interaction is a JSON object, not a
refactor.

Nothing here starts anything. It reads and writes preferences, and the daemon
asks it what was chosen.
"""
import json
import os
from pathlib import Path
import re

VERSION = 1
IDENTIFIER = re.compile(r'[a-z0-9][a-z0-9-]{0,47}')
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
REQUIRED = ('id', 'title', 'date', 'summary')
# Handlers the daemon can actually carry out. Everything else is a declared
# interaction waiting for its implementation, and is reported as such.
HANDLERS = ('bed',)
# Shipped as a file, but a desktop whose config was never deployed still gets a
# working feature rather than a traceback.
FALLBACK = {
    'version': VERSION,
    'enabled': False,
    'selected': 'bed',
    'interactions': [
        {'id': 'bed', 'title': 'Bed mode', 'date': '2026-09-09', 'handler': 'bed',
         'summary': 'The laptop runs warm on purpose while she is lying on it.',
         'detail': 'Mains only, under a hard ceiling, and it lets the lid close '
                   'without sleeping. Stop it any time with: oldbook-cat stop'},
    ],
    'work': [],
}


def config_path():
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'oldbook/cat.json'


def check(document):
    """Reject a registry rather than half-read one; ids stay unique."""
    if document.get('version') != VERSION or not isinstance(document.get('interactions'), list):
        raise ValueError('Unsupported cat registry: expected version 1 with an interactions list')
    seen = set()
    for entry in document['interactions']:
        if not isinstance(entry, dict) or any(not isinstance(entry.get(key), str)
                                              for key in REQUIRED):
            raise ValueError('Each interaction needs id, title, date and summary')
        if not IDENTIFIER.fullmatch(entry['id']) or entry['id'] in seen:
            raise ValueError('Invalid or duplicate interaction id: ' + entry['id'])
        if not DATE.fullmatch(entry['date']):
            raise ValueError('Interaction date must be YYYY-MM-DD: ' + entry['id'])
        seen.add(entry['id'])
    selected = document.get('selected')
    if selected is not None and selected not in seen:
        raise ValueError('Selected interaction is not in the list: ' + str(selected))
    return document


def load(path=None):
    """The registry, or the shipped fallback when there is no readable file."""
    path = config_path() if path is None else Path(path)
    try:
        document = json.loads(path.read_text())
    except (OSError, ValueError):
        return dict(FALLBACK)
    try:
        return check(document)
    except ValueError:
        return dict(FALLBACK)


def save(document, path=None):
    path = config_path() if path is None else Path(path)
    check(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(document, indent=2) + '\n')
    temporary.replace(path)
    return document


def entries(document=None):
    return list((document or load())['interactions'])


def find(identifier, document=None):
    for entry in entries(document):
        if entry['id'] == identifier:
            return entry
    return None


def selected(document=None):
    """The chosen entry, or None when the list is empty or nothing is chosen."""
    document = load() if document is None else document
    chosen = document.get('selected')
    return find(chosen, document) if chosen else None


def implemented(entry):
    return bool(entry) and entry.get('handler') in HANDLERS


def enabled(document=None):
    document = load() if document is None else document
    return bool(document.get('enabled'))


def select(identifier, path=None):
    document = load(path)
    if find(identifier, document) is None:
        raise ValueError('No such interaction: ' + identifier)
    document['selected'] = identifier
    return save(document, path)


def cycle(step=1, path=None):
    """Move the selection along the list, wrapping. This is 'cycled through'."""
    document = load(path)
    listed = [entry['id'] for entry in document['interactions']]
    if not listed:
        raise ValueError('There are no interactions to cycle through')
    try:
        index = listed.index(document.get('selected'))
    except ValueError:
        index = -step
    document['selected'] = listed[(index + step) % len(listed)]
    return save(document, path)


def add(entry, path=None, select_it=False):
    """Register a new interaction. This is 'generated' and 'managed'."""
    document = load(path)
    if find(entry.get('id', ''), document) is not None:
        raise ValueError('That interaction already exists: ' + entry['id'])
    document['interactions'].append(dict(entry))
    if select_it:
        document['selected'] = entry['id']
    return save(document, path)


def remove(identifier, path=None):
    document = load(path)
    if find(identifier, document) is None:
        raise ValueError('No such interaction: ' + identifier)
    document['interactions'] = [entry for entry in document['interactions']
                                if entry['id'] != identifier]
    if document.get('selected') == identifier:
        remaining = document['interactions']
        document['selected'] = remaining[0]['id'] if remaining else None
    return save(document, path)


def set_enabled(value, path=None):
    document = load(path)
    document['enabled'] = bool(value)
    return save(document, path)
