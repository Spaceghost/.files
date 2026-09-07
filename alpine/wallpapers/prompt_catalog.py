"""Scene and Space Ghost insertion selection shared by the generator and editor.

The catalog holds two independently switchable banks: ``scenes`` describe the
painting, ``insertions`` describe how Space Ghost enters it. Each entry can be
turned off without deleting it, and each bank picks entries with its own mode.
Every request also records the pair it painted so a later request can prefer a
combination the gallery has never shown.
"""
import datetime as dt
import json
import os
from pathlib import Path
import random
import re
import uuid

BANKS = ('scenes', 'insertions', 'mediums')
SELECTION_MODES = ('rotate', 'random', 'shuffle')
DEFAULT_MODE = 'shuffle'
MODE_KEYS = {'scenes': 'scene_selection', 'insertions': 'insertion_selection',
             'mediums': 'medium_selection'}
LIMITS = {'title': 120, 'description': 4000}


def valid_entry_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value) is not None


def validate(catalog):
    """Accept catalogs without the newer banks so older files keep working."""
    if not isinstance(catalog, dict) or not isinstance(catalog.get('style'), str):
        raise ValueError('Prompt file must contain a string style.')
    for bank in BANKS:
        items = catalog.get(bank)
        if items is None and bank != 'scenes':
            continue
        if not isinstance(items, list) or (bank == 'scenes' and not items):
            raise ValueError(f'Prompt file must contain at least one {bank[:-1]}.')
        identifiers = set()
        for item in items:
            if not isinstance(item, dict) or not valid_entry_id(item.get('id')):
                raise ValueError(f'Every {bank[:-1]} needs a lowercase hyphenated ID.')
            for key, limit in LIMITS.items():
                value = item.get(key)
                if not isinstance(value, str) or len(value) > limit:
                    raise ValueError(f'{bank[:-1].capitalize()} {item["id"]} needs a string {key}'
                                     f' of at most {limit} characters.')
            if 'enabled' in item and not isinstance(item['enabled'], bool):
                raise ValueError(f'{bank[:-1].capitalize()} {item["id"]} enabled must be true or false.')
            if item['id'] in identifiers:
                raise ValueError(f'Duplicate {bank[:-1]} ID: {item["id"]}')
            identifiers.add(item['id'])
        if bank == 'scenes' and not any(item.get('enabled', True) for item in items):
            raise ValueError('At least one scene must stay enabled.')
    for key in MODE_KEYS.values():
        if key in catalog and catalog[key] not in SELECTION_MODES:
            raise ValueError(f'{key} must be one of: ' + ', '.join(SELECTION_MODES))
    return catalog


def load_catalog(path):
    catalog = json.loads(Path(path).read_text())
    return validate(catalog)


def bank(catalog, name):
    return tuple(catalog.get(name) or ())


def enabled(catalog, name):
    """Disabling an entire bank falls back to all of it rather than painting nothing."""
    items = bank(catalog, name)
    active = tuple(item for item in items if item.get('enabled', True))
    return active or items


def selection_mode(catalog, name):
    mode = catalog.get(MODE_KEYS[name], DEFAULT_MODE)
    return mode if mode in SELECTION_MODES else DEFAULT_MODE


class PaintHistory:
    """Which scene/insertion pairs the gallery has already painted."""

    def __init__(self, path, records=None):
        self.path = Path(path)
        self.records = list(records or ())

    @classmethod
    def load(cls, path, bootstrap=()):
        path = Path(path)
        try:
            document = json.loads(path.read_text())
            records = document['records'] if isinstance(document, dict) else document
            if not isinstance(records, list):
                raise ValueError('history must be a list of records')
            return cls(path, [record for record in records if isinstance(record, dict)])
        except (OSError, ValueError, KeyError):
            # A missing or damaged history still honours what the gallery has painted.
            return cls(path, list(bootstrap))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        document = {'version': 1, 'records': self.records[-2000:]}
        temporary = self.path.with_name(f'{self.path.name}.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(document, indent=2) + '\n')
        temporary.replace(self.path)

    def record(self, scene_id, insertion_id, medium_id=None, seed=None):
        self.records.append({'scene': scene_id, 'insertion': insertion_id,
                             'medium': medium_id, 'seed': seed,
                             'painted_utc': dt.datetime.now(dt.timezone.utc).isoformat()})

    def pairs(self):
        return [(record.get('scene'), record.get('insertion'), record.get('medium'))
                for record in self.records]

    def used(self):
        return set(self.pairs())

    def last(self, name):
        key = {'scenes': 'scene', 'insertions': 'insertion', 'mediums': 'medium'}[name]
        for record in reversed(self.records):
            if record.get(key):
                return record[key]
        return None

    def last_use_index(self):
        return {pair: index for index, pair in enumerate(self.pairs())}


def _rotated(items, previous):
    """Order a bank so the entry after the last painted one comes first."""
    identifiers = [item['id'] for item in items]
    start = identifiers.index(previous) + 1 if previous in identifiers else 0
    return [items[(start + offset) % len(items)] for offset in range(len(items))]


def choose(catalog, history, *, scene_id=None, insertion_id=None, medium_id=None, rng=None):
    """Pick a scene, insertion and medium, preferring a set never painted before.

    ``rotate`` walks a bank in order, ``random`` draws freely, and ``shuffle``
    exhausts every enabled combination before any repeat. Explicit IDs win, and
    when everything has been painted the least recently used set returns.
    """
    rng = rng or random
    banks = {name: (_resolve(catalog, name, identifier) or [None])
             for name, identifier in (('scenes', scene_id), ('insertions', insertion_id),
                                      ('mediums', medium_id))}
    # A scene that parodies a specific painting carries its own medium, so it is
    # never paired with one from the bank.
    combinations = [(scene, insertion, None if (scene or {}).get('fixed_medium') else medium)
                    for scene in banks['scenes']
                    for insertion in banks['insertions']
                    for medium in banks['mediums']]
    combinations = list({_key(item): item for item in combinations}.values())
    if len(combinations) == 1:
        return combinations[0]
    used = history.used()
    fresh = [item for item in combinations if _key(item) not in used]
    modes = {name: selection_mode(catalog, name) for name in BANKS}
    if 'rotate' in modes.values():
        ordered = _rotation_order(banks, history, modes)
        available = {_key(item) for item in fresh}
        preferred = [item for item in ordered if _key(item) in available]
        return (preferred or ordered)[0]
    if fresh:
        return rng.choice(fresh)
    recency = history.last_use_index()
    return min(combinations, key=lambda item: recency.get(_key(item), -1))


def _key(combination):
    return tuple(entry['id'] if entry else None for entry in combination)


def _resolve(catalog, name, identifier):
    items = enabled(catalog, name)
    if identifier is None:
        return list(items)
    chosen = next((item for item in bank(catalog, name) if item['id'] == identifier), None)
    if chosen is None:
        raise RuntimeError(f'Unknown {name[:-1]}: {identifier}')
    return [chosen]


def _rotation_order(banks, history, modes):
    ordered = {}
    for name, items in banks.items():
        present = [item for item in items if item]
        if modes[name] == 'rotate' and present:
            ordered[name] = _rotated(present, history.last(name))
        else:
            ordered[name] = items
    combinations = [(scene, insertion, None if (scene or {}).get('fixed_medium') else medium)
                    for scene in ordered['scenes']
                    for insertion in ordered['insertions']
                    for medium in ordered['mediums']]
    return list({_key(item): item for item in combinations}.values())


def variation_seed():
    return uuid.uuid4().hex


def compose_prompt(catalog, theme, scene, insertion, medium, seed):
    """Build the exact request, recorded verbatim in the artwork sidecar."""
    prompt = catalog['style']
    if theme.get('image_style'):
        prompt += '\n\nTheme: ' + theme['name'] + '. ' + theme['image_style']
    if medium:
        prompt += '\n\nMedium and treatment: ' + medium['description']
    prompt += '\n\nSubject: ' + scene['description']
    if insertion:
        prompt += '\n\nSpace Ghost insertion style: ' + insertion['description']
    prompt += ('\n\nThis image joins a long running series. Compose it so it could never be '
               'mistaken for an earlier version of the same subject: choose a fresh viewpoint, '
               'hour, weather and arrangement of figures rather than repeating an obvious '
               'composition. Variation seed: ' + seed)
    return prompt
