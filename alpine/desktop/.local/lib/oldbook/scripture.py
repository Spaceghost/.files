"""Offline King James text, reference parsing and the reflection catalogue.

The bundled verse file is one tab separated record per line, so a search is a
single pass and a lookup needs no database. Reflections are curated entries
about Christ and about what particular believers endured; each names an anchor
verse that is resolved from the same verse file.
"""
import datetime as dt
import gzip
import json
from pathlib import Path
import re
import unicodedata

VERSE_FILE = 'kjv.tsv.gz'
REFLECTION_FILE = 'reflections.json'
WITNESS_FILE = 'witnesses.json'
BUNDLED = 'kjv'
# Downloaded translations and Jewish texts live outside the checkout.
INSTALL_ROOT = Path.home() / '.local/share/oldbook/scripture'

# Ordinals are spelled many ways; everything collapses to a compact key.
ORDINALS = {'first': '1', 'second': '2', 'third': '3', 'i': '1', 'ii': '2', 'iii': '3'}
ALIASES = {
    'ps': 'psalms', 'psalm': 'psalms', 'prov': 'proverbs', 'eccl': 'ecclesiastes',
    'song': 'songofsolomon', 'songofsongs': 'songofsolomon', 'canticles': 'songofsolomon',
    'matt': 'matthew', 'mk': 'mark', 'lk': 'luke', 'jn': 'john', 'phil': 'philippians',
    'philem': 'philemon', 'rev': 'revelation', 'apocalypse': 'revelation',
    'deut': 'deuteronomy', 'josh': 'joshua', 'judg': 'judges', 'lam': 'lamentations',
    'ezek': 'ezekiel', 'dan': 'daniel', 'hab': 'habakkuk', 'zech': 'zechariah',
    'mal': 'malachi', 'rom': 'romans', 'gal': 'galatians', 'eph': 'ephesians',
    'col': 'colossians', 'thess': 'thessalonians', 'tim': 'timothy', 'heb': 'hebrews',
}


def normalise(value):
    """Fold a book name or query to a comparable key."""
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '', text.lower())


class Bible:
    def __init__(self, verses):
        self.verses = verses
        self.books = []
        self._by_book = {}
        for record in verses:
            if record['book'] not in self._by_book:
                self._by_book[record['book']] = []
                self.books.append(record['book'])
            self._by_book[record['book']].append(record)
        self._names = {normalise(name): name for name in self.books}
        self._names.update({normalise(name.removeprefix('Talmud ')): name
                            for name in self.books if name.startswith('Talmud ')})

    @staticmethod
    def resolve(directory, translation=BUNDLED):
        """The bundled King James text, or an installed one by identifier."""
        if translation in (None, '', BUNDLED):
            return Path(directory) / VERSE_FILE
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', str(translation)):
            raise ValueError('Unusable translation identifier: ' + str(translation))
        for candidate in (INSTALL_ROOT / f'{translation}.tsv.gz',
                          Path(directory) / f'{translation}.tsv.gz'):
            if candidate.is_file():
                return candidate
        raise ValueError(f'{translation} is not installed; run '
                         'oldbook-scripture-library install ' + str(translation))

    @classmethod
    def load(cls, directory, include_extra=True, translation=BUNDLED):
        path = cls.resolve(directory, translation)
        verses = []
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                book, chapter, verse, text = line.rstrip('\n').split('\t', 3)
                verses.append({'book': book, 'chapter': int(chapter),
                               'verse': int(verse), 'text': text})
        if not verses:
            raise ValueError('Verse file is empty')
        extra = Path(directory) / 'jewish-texts.jsonl.gz'
        # The bundled extras belong to the default view; asking for a specific
        # translation should return that translation and nothing else.
        if include_extra and translation in (None, '', BUNDLED) and extra.exists():
            with gzip.open(extra, 'rt', encoding='utf-8') as handle:
                verses.extend(json.loads(line) for line in handle)
        return cls(verses)

    def resolve_book(self, token):
        """Match a book by exact name, known abbreviation, or unique prefix.

        The spelling as written is always tried first, so a book beginning with
        an ordinal-looking letter such as Isaiah is never read as "I Saiah".
        """
        key = normalise(re.sub(r'^Bible\s+', '', token, flags=re.IGNORECASE))
        if not key:
            return None
        for candidate in self._candidates(key):
            resolved = self._match(candidate)
            if resolved:
                return resolved
        return None

    @staticmethod
    def _candidates(key):
        yield key
        if key in ALIASES:
            yield ALIASES[key]
        words = re.match(r'^(first|second|third|i{1,3})([a-z].+)$', key)
        if words and words.group(1) in ORDINALS:
            rest = words.group(2)
            yield ORDINALS[words.group(1)] + rest
            yield ORDINALS[words.group(1)] + ALIASES.get(rest, rest)
        number = re.match(r'^([1-3])(.+)$', key)
        if number:
            yield number.group(1) + ALIASES.get(number.group(2), number.group(2))

    def _match(self, key):
        if key in self._names:
            return self._names[key]
        matches = sorted({name for normalised, name in self._names.items()
                          if normalised.startswith(key)})
        return matches[0] if len(matches) == 1 else None

    def chapter(self, book, number):
        return [record for record in self._by_book.get(book, []) if record['chapter'] == number]

    def chapter_count(self, book):
        return max((record['chapter'] for record in self._by_book.get(book, [])), default=0)

    def lookup(self, reference):
        """Return the verses named by a reference such as ``Isaiah 53:3-5``."""
        parsed = parse_reference(reference)
        if parsed is None:
            return []
        name, chapter, first, last = parsed
        book = self.resolve_book(name)
        if book is None:
            return []
        if chapter is None:
            return self.chapter(book, self._by_book[book][0]['chapter'])
        records = self.chapter(book, chapter)
        if first is None:
            # Obadiah, Philemon, 2-3 John and Jude are cited by verse, not chapter.
            if not records and self.chapter_count(book) == 1:
                return [record for record in self.chapter(book, 1)
                        if record['verse'] == chapter]
            return records
        last = last or first
        return [record for record in records if first <= record['verse'] <= last]

    def search(self, query, limit=60):
        """Find verses containing every word of the query, reference first."""
        direct = self.lookup(query)
        if direct:
            return direct[:limit]
        words = [word for word in re.findall(r"[a-z']+", query.lower()) if len(word) > 1]
        if not words:
            return []
        results = []
        for record in self.verses:
            lowered = record['text'].lower()
            if all(word in lowered for word in words):
                results.append(record)
                if len(results) >= limit:
                    break
        return results


def parse_reference(text):
    """Split ``1 Cor 13:4-7`` into its book, chapter and verse range."""
    if not isinstance(text, str):
        return None
    match = re.fullmatch(
        r"\s*((?:[1-3]|first|second|third|i{1,3})?\s*[A-Za-z][A-Za-z'.\s]*?)"
        r"(?:\s+(\d+[ab]?))?(?:\s*[:.]\s*(\d+)(?:\s*[-–]\s*(\d+))?)?\s*",
        text, re.IGNORECASE)
    if not match:
        return None
    name, chapter, first, last = match.groups()
    if not normalise(name):
        return None
    return (name.strip(), (int(chapter) if chapter.isdigit() else chapter.lower()) if chapter else None,
            int(first) if first else None, int(last) if last else None)


def format_reference(records):
    if not records:
        return ''
    first, last = records[0], records[-1]
    if first is last:
        return f"{first['book']} {first['chapter']}:{first['verse']}"
    if first['chapter'] != last['chapter']:
        return f"{first['book']} {first['chapter']}:{first['verse']}-{last['chapter']}:{last['verse']}"
    return f"{first['book']} {first['chapter']}:{first['verse']}-{last['verse']}"


def passage_text(records):
    return ' '.join(record['text'] for record in records)


def available_translations(directory, root=None):
    """Every text this machine can open, bundled first."""
    root = Path(root or INSTALL_ROOT)
    found = [{'id': BUNDLED, 'title': 'King James Version', 'collection': 'Christian Bible',
              'license': 'Public domain'}]
    if not root.is_dir():
        return found
    for meta in sorted(root.glob('*.json')):
        if not (root / f'{meta.stem}.tsv.gz').is_file():
            continue
        try:
            record = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        found.append({'id': meta.stem, 'title': record.get('title', meta.stem),
                      'collection': record.get('collection', ''),
                      'license': record.get('license', '')})
    return found


def load_witnesses(directory):
    """Remarks about the faith from people who did not hold it."""
    document = json.loads((Path(directory) / WITNESS_FILE).read_text())
    quotes = document.get('quotes')
    if not isinstance(quotes, list) or not quotes:
        raise ValueError('Witness file must contain a non-empty list')
    seen = set()
    for entry in quotes:
        for key in ('id', 'quote', 'author', 'source', 'note', 'stance'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f'Witness quote is missing {key}')
        if entry['id'] in seen:
            raise ValueError('Duplicate witness id: ' + entry['id'])
        seen.add(entry['id'])
    return quotes


def daily_witness(quotes, today=None):
    today = today or dt.date.today()
    return quotes[today.toordinal() % len(quotes)]


def load_reflections(directory):
    document = json.loads((Path(directory) / REFLECTION_FILE).read_text())
    entries = document.get('reflections')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Reflection file must contain a non-empty list')
    seen = set()
    for entry in entries:
        for key in ('id', 'figure', 'title', 'reference', 'trial', 'reflection', 'practice'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f'Reflection is missing {key}')
        if entry['id'] in seen:
            raise ValueError('Duplicate reflection id: ' + entry['id'])
        seen.add(entry['id'])
    return entries


def figures(reflections):
    return sorted({entry['figure'] for entry in reflections})


def search_reflections(reflections, query):
    """Match a reflection by figure, title, reference or body text."""
    key = normalise(query)
    if not key:
        return list(reflections)
    scored = []
    for entry in reflections:
        haystacks = (entry['figure'], entry['title'], entry['reference'],
                     entry['trial'], entry['reflection'], entry['practice'])
        keys = [normalise(value) for value in haystacks]
        if keys[0] == key or keys[0].startswith(key):
            scored.append((0, entry))
        elif any(key in value for value in keys[:3]):
            scored.append((1, entry))
        elif any(key in value for value in keys[3:]):
            scored.append((2, entry))
    return [entry for _rank, entry in sorted(scored, key=lambda pair: pair[0])]


def daily_reflection(reflections, today=None):
    """A stable choice for the day that still visits every entry in turn."""
    today = today or dt.date.today()
    return reflections[today.toordinal() % len(reflections)]


def rotating_reflection(reflections, index):
    return reflections[index % len(reflections)]
