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

BANKS = ('scenes', 'insertions')
SELECTION_MODES = ('rotate', 'random', 'shuffle')
DEFAULT_MODE = 'shuffle'
MODE_KEYS = {'scenes': 'scene_selection', 'insertions': 'insertion_selection'}
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

    def record(self, scene_id, insertion_id, seed=None):
        self.records.append({'scene': scene_id, 'insertion': insertion_id, 'seed': seed,
                             'painted_utc': dt.datetime.now(dt.timezone.utc).isoformat()})

    def pairs(self):
        return [(record.get('scene'), record.get('insertion')) for record in self.records]

    def used(self):
        return set(self.pairs())

    def last(self, name):
        key = 'scene' if name == 'scenes' else 'insertion'
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


def choose(catalog, history, *, scene_id=None, insertion_id=None, rng=None):
    """Pick a scene and insertion, preferring a pair the gallery has never painted.

    ``rotate`` walks both banks in order, ``random`` draws freely, and ``shuffle``
    exhausts every enabled pair before any repeat. When explicit IDs are given they
    win, and when every pair has been painted the least recently used one returns.
    """
    rng = rng or random
    scenes = _resolve(catalog, 'scenes', scene_id)
    insertions = _resolve(catalog, 'insertions', insertion_id) or [None]
    pairs = [(scene, insertion) for scene in scenes for insertion in insertions]
    if len(pairs) == 1:
        return pairs[0]
    used = history.used()
    fresh = [pair for pair in pairs if _key(pair) not in used]
    scene_mode = selection_mode(catalog, 'scenes')
    insertion_mode = selection_mode(catalog, 'insertions')
    if scene_mode == 'rotate' or insertion_mode == 'rotate':
        ordered = _rotation_order(scenes, insertions, history, scene_mode, insertion_mode)
        preferred = [pair for pair in ordered if _key(pair) in {_key(p) for p in fresh}]
        return (preferred or ordered)[0]
    if fresh and (scene_mode == 'shuffle' or insertion_mode == 'shuffle'):
        return rng.choice(fresh)
    if fresh:
        return rng.choice(fresh)
    recency = history.last_use_index()
    return min(pairs, key=lambda pair: recency.get(_key(pair), -1))


def _key(pair):
    scene, insertion = pair
    return (scene['id'], insertion['id'] if insertion else None)


def _resolve(catalog, name, identifier):
    items = enabled(catalog, name)
    if identifier is None:
        return list(items)
    chosen = next((item for item in bank(catalog, name) if item['id'] == identifier), None)
    if chosen is None:
        raise RuntimeError(f'Unknown {name[:-1]}: {identifier}')
    return [chosen]


def _rotation_order(scenes, insertions, history, scene_mode, insertion_mode):
    scene_order = (_rotated(scenes, history.last('scenes')) if scene_mode == 'rotate'
                   else list(scenes))
    insertion_order = (_rotated([i for i in insertions if i], history.last('insertions'))
                       if insertion_mode == 'rotate' and any(insertions) else list(insertions))
    return [(scene, insertion) for scene in scene_order for insertion in (insertion_order or [None])]


def variation_seed():
    return uuid.uuid4().hex


def compose_prompt(catalog, theme, scene, insertion, seed):
    """Build the exact painting request, recorded verbatim in the artwork sidecar."""
    prompt = catalog['style']
    if theme.get('image_style'):
        prompt += '\n\nTheme: ' + theme['name'] + '. ' + theme['image_style']
    prompt += '\n\nScene: ' + scene['description']
    if insertion:
        prompt += '\n\nSpace Ghost insertion style: ' + insertion['description']
    prompt += ('\n\nThis painting joins a long running series. Compose it so it could never be '
               'mistaken for an earlier version of the same scene: choose a fresh viewpoint, '
               'hour, weather and arrangement of figures rather than repeating an obvious '
               'composition. Variation seed: ' + seed)
    return prompt
