"""Durable, append-only Scripture selections and their accompanying material.

This database is personal history, independent of the disposable study cache.
Never rebuild it from the versioned catalog.
"""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time

APPLICATION_ID = 0x4F425348
INTERVAL = 3600


def database_path():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'mbp-intel/scripture/history.sqlite3'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def instant(now):
    value = time.time() if now is None else float(now)
    if not math.isfinite(value) or value < 0:
        raise ValueError('History timestamp must be a finite Unix time')
    return value


@contextmanager
def connect(database=None):
    path = Path(database) if database is not None else database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Scripture history must not be a symlink')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(path, timeout=30, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            identity = db.execute('PRAGMA application_id').fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if identity != APPLICATION_ID and (identity or tables):
                raise ValueError('Refusing foreign Scripture history database')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported Scripture history schema')
            if not tables:
                db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                db.execute('PRAGMA user_version=1')
                for statement in (
                    'CREATE TABLE entries (id INTEGER PRIMARY KEY, selected_at REAL NOT NULL, '
                    'selected_utc TEXT NOT NULL, reason TEXT NOT NULL, fingerprint TEXT NOT NULL, document TEXT NOT NULL)',
                    'CREATE TABLE current (singleton INTEGER PRIMARY KEY CHECK(singleton=1), '
                    'entry_id INTEGER NOT NULL REFERENCES entries(id), next_at REAL NOT NULL)',
                    'CREATE TABLE additions (id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL REFERENCES entries(id), '
                    'created_at REAL NOT NULL, created_utc TEXT NOT NULL, kind TEXT NOT NULL, '
                    'fingerprint TEXT NOT NULL, document TEXT NOT NULL, UNIQUE(entry_id,fingerprint))',
                ):
                    db.execute(statement)
                for table in ('entries', 'additions'):
                    for operation in ('UPDATE', 'DELETE'):
                        db.execute(f"CREATE TRIGGER {table}_{operation.lower()} BEFORE {operation} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT, 'Scripture history is append-only'); END")
            db.execute('COMMIT')
            yield db
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise


def record(row):
    if row is None:
        return None
    result = dict(row)
    result['document'] = json.loads(result['document'])
    return result


def _current(db):
    return record(db.execute('SELECT entries.*, current.next_at FROM current '
                             'JOIN entries ON entries.id=current.entry_id WHERE singleton=1').fetchone())


def _select(db, document, reason, now):
    document = dict(document)
    for key in ('history_id', 'chosen_utc', 'next_at'):
        document.pop(key, None)
    if (not document.get('reference') or not isinstance(document.get('text'), str)
            or not document['text'].strip()):
        raise ValueError('History needs a materialized passage and reference')
    encoded = encode(document)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    previous = _current(db)
    if previous and previous['fingerprint'] == fingerprint:
        identifier = previous['id']
    else:
        identifier = db.execute('INSERT INTO entries(selected_at,selected_utc,reason,fingerprint,document) '
                                'VALUES(?,?,?,?,?)', (now, utc(now), reason, fingerprint, encoded)).lastrowid
    db.execute('INSERT INTO current VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE '
               'SET entry_id=excluded.entry_id,next_at=excluded.next_at', (identifier, now + INTERVAL))
    return _current(db)


def select(document, database=None, now=None, reason='manual'):
    with connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        result = _select(db, document, reason, instant(now))
        db.execute('COMMIT')
        return result


def advance(initial, following, database=None, now=None, force=False):
    """Choose once per observed hour, or once per explicit Next operation.

    Callbacks run under the same transaction as the due check. Concurrent card
    refreshes cannot advance twice, and suspended hours are never fabricated.
    """
    now = instant(now)
    with connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        previous = _current(db)
        if previous is None:
            result = _select(db, initial(), 'initial', now)
        elif force or now >= previous['next_at']:
            result = _select(db, following(previous['document']), 'manual-next' if force else 'hourly', now)
        else:
            result = previous
        db.execute('COMMIT')
        return result


def current(database=None):
    with connect(database) as db:
        return _current(db)


def entries(database=None, before=None, limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError('History page size must be between 1 and 1000')
    with connect(database) as db:
        return [record(row) for row in db.execute('SELECT * FROM entries WHERE (? IS NULL OR id<?) '
                                                 'ORDER BY id DESC LIMIT ?', (before, before, limit))]


def get(identifier, database=None):
    with connect(database) as db:
        result = record(db.execute('SELECT * FROM entries WHERE id=?', (identifier,)).fetchone())
        if result is None:
            raise ValueError('No Scripture history entry ' + str(identifier))
        result['additions'] = [record(row) for row in db.execute(
            'SELECT * FROM additions WHERE entry_id=? ORDER BY id', (identifier,))]
        return result


def adjacent(identifier, direction, database=None):
    if direction not in ('older', 'newer'):
        raise ValueError('History direction must be older or newer')
    comparison, order = ('<', 'DESC') if direction == 'older' else ('>', 'ASC')
    with connect(database) as db:
        row = db.execute(f'SELECT id FROM entries WHERE id{comparison}? ORDER BY id {order} LIMIT 1',
                         (identifier,)).fetchone()
        return row[0] if row else None


def append(identifier, document, kind='note', database=None, now=None):
    if kind not in ('note', 'research', 'generated', 'study'):
        raise ValueError('Extra material must be note, research, generated, or study')
    if not isinstance(document, dict) or not (document.get('text') or document.get('reflection')):
        raise ValueError('Extra material must contain text')
    encoded = encode(document)
    fingerprint = hashlib.sha256((kind + '\0' + encoded).encode()).hexdigest()
    now = instant(now)
    with connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM entries WHERE id=?', (identifier,)).fetchone():
            raise ValueError('No Scripture history entry ' + str(identifier))
        db.execute('INSERT OR IGNORE INTO additions(entry_id,created_at,created_utc,kind,fingerprint,document) '
                   'VALUES(?,?,?,?,?,?)', (identifier, now, utc(now), kind, fingerprint, encoded))
        result = db.execute('SELECT id FROM additions WHERE entry_id=? AND fingerprint=?',
                            (identifier, fingerprint)).fetchone()[0]
        db.execute('COMMIT')
        return result


def backup(destination, database=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with connect(database) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise sqlite3.DatabaseError('Scripture history backup failed integrity check')
    return destination


def render(entry):
    """Full reading text and useful attribution; exact metadata stays exportable."""
    document = entry['document']
    lines = [document.get('reference', ''), entry['selected_utc'] + ' · ' + entry['reason'], '']

    def material(value):
        for key in ('title', 'edition', 'text', 'figure', 'trial', 'reflection', 'practice'):
            if value.get(key):
                lines.extend([key.replace('_', ' ').title() + ':'] if key not in ('title', 'text') else [])
                lines.extend([str(value[key]), ''])
        if value.get('source_url'):
            lines.append('Passage source: ' + str(value['source_url']))
        if value.get('license'):
            lines.extend(['License: ' + str(value['license']), ''])
        for source in value.get('sources', []):
            if not isinstance(source, dict):
                continue
            lines.append('Source: ' + str(source.get('title', 'Untitled source')))
            if source.get('url'):
                lines.append(str(source['url']))
            if source.get('license'):
                lines.append('License: ' + str(source['license']))
            if source.get('text'):
                lines.extend(['', str(source['text'])])
            lines.append('')
        provenance = value.get('provenance', {})
        if isinstance(provenance, dict):
            for key, label in (('method', 'Method'), ('model', 'Model'), ('created_utc', 'Created'),
                               ('author', 'Author'), ('description', 'Provenance')):
                if provenance.get(key):
                    lines.append(label + ': ' + str(provenance[key]))
            if provenance:
                lines.append('')

    material(document)
    for addition in entry.get('additions', []):
        lines.extend(['─' * 48, addition['created_utc'] + ' · ' + addition['kind'], ''])
        material(addition['document'])
    return '\n'.join(lines)
