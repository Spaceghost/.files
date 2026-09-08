"""Prefer nocturne paintings after dark without ever hiding a painting.

Only the automatic rotation timer consults this; manual browsing, explicit
picks and refreshes never do. With no configured location, in daylight, or in
a gallery without a single nocturne, it declines and the ordinary sequential
choice proceeds unchanged.
"""
import datetime as dt
import random
import re

import astro

NIGHT_WEIGHT = 3
NIGHT_WORDS = frozenset((
    'night', 'nights', 'nightfall', 'moon', 'moonlight', 'moonlit', 'nocturne',
    'nocturnal', 'dusk', 'stars', 'starry', 'starlight', 'candle', 'candles',
    'candlelight', 'candlelit', 'lantern', 'lanterns', 'midnight', 'aurora',
))
TEXT_FIELDS = ('title', 'description', 'scene', 'scene_description', 'note')
WORD = re.compile(r'[a-z]+')


def is_nocturne(entry):
    """An explicit ``time_of_day`` wins; otherwise conservative whole words."""
    tag = entry.get('time_of_day')
    if isinstance(tag, str) and tag.strip():
        return tag.strip().lower() == 'night'
    words = set()
    for field in TEXT_FIELDS:
        value = entry.get(field)
        if isinstance(value, str):
            words.update(WORD.findall(value.lower()))
    return not words.isdisjoint(NIGHT_WORDS)


def nocturne_preference(entries, current, *, now=None, location=None, rng=None):
    """Return the id of a weighted random next painting after dark, else None."""
    if location is None:
        location = astro.load_location()
    if location is None:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    if not astro.is_night(now, location):
        return None
    candidates = [entry for entry in entries
                  if entry.get('id') and entry.get('id') != current]
    if not candidates or not any(is_nocturne(entry) for entry in candidates):
        return None
    weights = [NIGHT_WEIGHT if is_nocturne(entry) else 1 for entry in candidates]
    chooser = rng if rng is not None else random
    return chooser.choices(candidates, weights=weights, k=1)[0]['id']
