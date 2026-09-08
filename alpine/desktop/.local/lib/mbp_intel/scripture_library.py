"""Convert downloaded scripture sources into the on-device verse format.

Everything ends up as the same gzipped, tab separated record used by the
bundled King James text, so one reader serves every translation and every
Jewish text. Nothing here touches the network; the caller supplies the bytes.
"""
import gzip
import hashlib
import html
import json
from pathlib import Path
import re

RECORD_FIELDS = ('book', 'chapter', 'verse', 'text')
INSTALL_ROOT = Path.home() / '.local/share/mbp-intel/scripture'
SAFE_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')


def clean(text):
    """Sefaria and getbible both ship HTML; the verse file holds plain text."""
    text = re.sub(r'<sup[^>]*>.*?</sup>', '', str(text), flags=re.S)
    text = re.sub(r'<i class="footnote".*?</i>', '', text, flags=re.S)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = text.replace('\t', ' ').replace('\n', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def getbible_rows(document):
    """Rows from a getbible.net v2 whole-translation document."""
    books = document.get('books')
    if not isinstance(books, list) or not books:
        raise ValueError('getbible document has no books')
    rows = []
    for book in books:
        name = str(book.get('name', '')).strip()
        if not name:
            raise ValueError('getbible book is missing its name')
        for chapter in book.get('chapters', []):
            for verse in chapter.get('verses', []):
                text = clean(verse.get('text', ''))
                if not text:
                    continue
                rows.append((name, int(chapter['chapter']), int(verse['verse']), text))
    if not rows:
        raise ValueError('getbible document produced no verses')
    return rows


def sefaria_rows(book, document, section_base=1):
    """Rows from one Sefaria API v3 text response for a whole book.

    ``section_base`` is 1 for chaptered books. Talmud tractates are cited by
    daf starting at 2a, and Sefaria indexes them so that the array position is
    the daf number, so those are numbered from 0.
    """
    versions = document.get('versions')
    if not isinstance(versions, list) or not versions:
        raise ValueError(f'Sefaria returned no version for {book}')
    version = versions[0]
    sections = version.get('text')
    if not isinstance(sections, list):
        raise ValueError(f'Sefaria returned no text for {book}')
    rows = []
    for chapter_index, section in enumerate(sections, start=section_base):
        entries = section if isinstance(section, list) else [section]
        for verse_index, entry in enumerate(entries, start=1):
            if isinstance(entry, list):
                entry = ' '.join(str(part) for part in entry)
            text = clean(entry)
            if text:
                rows.append((book, chapter_index, verse_index, text))
    return rows, version


def write_text(rows, path):
    """Write the gzipped verse file deterministically and return its digest."""
    if not rows:
        raise ValueError('Refusing to write an empty text')
    lines = []
    for book, chapter, verse, text in rows:
        if '\t' in book or '\t' in text:
            raise ValueError('A record may not contain a tab')
        lines.append(f'{book}\t{int(chapter)}\t{int(verse)}\t{text}')
    payload = ('\n'.join(lines) + '\n').encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    # A fixed mtime and an empty stored name keep the artefact byte-identical
    # when rebuilt from the same source, whatever it is called on disk.
    with open(temporary, 'wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', compresslevel=9,
                           fileobj=raw, mtime=0) as handle:
            handle.write(payload)
    temporary.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest(), len(rows)


def load_manifest(path):
    document = json.loads(Path(path).read_text())
    texts = document.get('texts')
    if not isinstance(texts, list) or not texts:
        raise ValueError('Library manifest must list texts')
    seen = set()
    for text in texts:
        if not isinstance(text, dict) or not SAFE_ID.fullmatch(str(text.get('id', ''))):
            raise ValueError('Every text needs a lowercase hyphenated id')
        if text['id'] in seen:
            raise ValueError('Duplicate text id: ' + text['id'])
        seen.add(text['id'])
        for key in ('title', 'source', 'license', 'collection'):
            if not isinstance(text.get(key), str) or not text[key].strip():
                raise ValueError(f'Text {text["id"]} needs a {key}')
        if text['source'] not in ('getbible', 'sefaria', 'bundled'):
            raise ValueError(f'Text {text["id"]} has an unknown source')
        if text['source'] == 'getbible' and not text.get('translation'):
            raise ValueError(f'Text {text["id"]} needs a getbible translation')
        if text['source'] == 'sefaria' and not isinstance(text.get('books'), list):
            raise ValueError(f'Text {text["id"]} needs a Sefaria book list')
    return document


def installed_texts(root=None):
    """Everything already on this machine, newest format only."""
    root = Path(root or INSTALL_ROOT)
    found = {}
    if not root.is_dir():
        return found
    for meta in sorted(root.glob('*.json')):
        try:
            record = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        if (root / f'{meta.stem}.tsv.gz').is_file():
            found[meta.stem] = record
    return found


def record_installation(text, digest, verses, root=None, path=None):
    root = Path(root or INSTALL_ROOT)
    record = {'id': text['id'], 'title': text['title'], 'collection': text['collection'],
              'license': text['license'], 'source': text['source'],
              'sha256': digest, 'verses': verses}
    if path is not None:
        record['file'] = str(path)
    (root / f"{text['id']}.json").write_text(json.dumps(record, indent=2) + '\n')
    return record
