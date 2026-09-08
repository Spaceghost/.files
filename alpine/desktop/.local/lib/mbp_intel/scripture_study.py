"""Versioned Scripture study entries with a disposable SQLite read cache."""
from contextlib import closing
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from urllib.parse import urlsplit

import scripture


SCHEMA_VERSION = 1
APPLICATION_ID = 0x4F425354  # "OBST" (MBP Intel Scripture Study)
KINDS = {'study-note', 'inspiration', 'observation'}
TEXT_FIELDS = ('figure', 'title', 'reference', 'trial', 'reflection', 'practice')
ENTRY_FIELDS = {
    'schema', 'id', 'kind', *TEXT_FIELDS, 'cited_source_ids', 'sources', 'provenance'
}
SOURCE_FIELDS = {'id', 'title', 'url', 'license', 'text', 'sha256'}
PROVENANCE_FIELDS = {
    'method', 'model', 'model_digest', 'endpoint', 'created_utc', 'prompt_sha256'
}
HEX64 = re.compile(r'[0-9a-f]{64}')
ENTRY_ID = re.compile(r'study-[0-9a-f]{32}')


def _database_path(database):
    if database is not None:
        return Path(database)
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return data / 'mbp-intel/scripture/study.sqlite3'


def _canonical_sources(assets):
    assets = Path(assets)
    paths = [assets / scripture.REFLECTION_FILE]
    paths.extend(sorted((assets / 'study/entries').glob('*.json')))
    digest = hashlib.sha256(f'scripture-study-schema:{SCHEMA_VERSION}\0'.encode())
    sources = []
    for path in paths:
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ValueError(f'Cannot read canonical Scripture source {path}: {error}') from error
        name = path.relative_to(assets).as_posix().encode()
        digest.update(len(name).to_bytes(8, 'big'))
        digest.update(name)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
        sources.append((path, content))
    return digest.hexdigest(), sources


def _require_fields(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing:
        raise ValueError(f'{label} is missing {sorted(missing)[0]}')
    if extra:
        raise ValueError(f'{label} has unsupported field {sorted(extra)[0]}')


def _valid_utc(value):
    if not isinstance(value, str) or not value.endswith('Z'):
        return False
    try:
        datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        return False
    return True


def _validate_entry(entry, path=None):
    label = f'Study entry {path}' if path else 'Study entry'
    _require_fields(entry, ENTRY_FIELDS, label)
    if entry['schema'] != SCHEMA_VERSION:
        raise ValueError(f'{label} has unsupported schema')
    if not isinstance(entry['id'], str) or not ENTRY_ID.fullmatch(entry['id']):
        raise ValueError(f'{label} has invalid id')
    if path is not None and Path(path).stem != entry['id']:
        raise ValueError(f'{label} id does not match its filename')
    if entry['kind'] not in KINDS:
        raise ValueError(f'{label} has invalid kind')
    for field in TEXT_FIELDS:
        if not isinstance(entry[field], str):
            raise ValueError(f'{label} field {field} must be text')
    for field in ('title', 'reference', 'reflection'):
        if not entry[field].strip():
            raise ValueError(f'{label} field {field} must not be empty')
    if not isinstance(entry['sources'], list) or not entry['sources']:
        raise ValueError(f'{label} sources must be a non-empty list')
    source_ids = []
    for source in entry['sources']:
        _require_fields(source, SOURCE_FIELDS, f'{label} source')
        for field in SOURCE_FIELDS:
            if not isinstance(source[field], str) or not source[field].strip():
                raise ValueError(f'{label} source {field} must not be empty')
        parsed_url = urlsplit(source['url'])
        if parsed_url.scheme != 'https' or not parsed_url.netloc:
            raise ValueError(f'{label} source URL must use HTTPS')
        actual = hashlib.sha256(source['text'].encode('utf-8')).hexdigest()
        if not HEX64.fullmatch(source['sha256']) or source['sha256'] != actual:
            raise ValueError(f'{label} source sha256 does not match its text')
        source_ids.append(source['id'])
    if len(source_ids) != len(set(source_ids)):
        raise ValueError(f'{label} source ids must be unique')
    cited = entry['cited_source_ids']
    if (not isinstance(cited, list) or not cited
            or not all(isinstance(item, str) and item.strip() for item in cited)
            or len(cited) != len(set(cited)) or not set(cited).issubset(source_ids)):
        raise ValueError(f'{label} cited_source_ids must be unique known source ids')
    provenance = entry['provenance']
    _require_fields(provenance, PROVENANCE_FIELDS, f'{label} provenance')
    if provenance['method'] != 'local-ollama':
        raise ValueError(f'{label} provenance method must be local-ollama')
    for field in PROVENANCE_FIELDS - {'method', 'created_utc', 'prompt_sha256'}:
        if not isinstance(provenance[field], str) or not provenance[field].strip():
            raise ValueError(f'{label} provenance {field} must not be empty')
    if not _valid_utc(provenance['created_utc']):
        raise ValueError(f'{label} provenance created_utc must be UTC')
    if not isinstance(provenance['prompt_sha256'], str) or not HEX64.fullmatch(
            provenance['prompt_sha256']):
        raise ValueError(f'{label} provenance prompt_sha256 is invalid')
    if any('${' in value for value in _strings(entry)):
        raise ValueError(f'{label} contains a Conky control sequence')
    return entry


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _catalog(assets, sources):
    entries = []
    for reflection in scripture.load_reflections(assets):
        item = dict(reflection)
        item['kind'] = 'reflection'
        entries.append(item)
    for path, content in sources[1:]:
        try:
            entry = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f'Unreadable study entry {path}: {error}') from error
        entries.append(_validate_entry(entry, path))
    identifiers = [entry['id'] for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Duplicate Scripture study entry id')
    return entries


def _read_cache(database, canonical_hash):
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(database, timeout=5)) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            row = db.execute("SELECT value FROM metadata WHERE key='canonical_hash'").fetchone()
            if version != SCHEMA_VERSION or row is None or row[0] != canonical_hash:
                return None
            return [json.loads(row[0]) for row in
                    db.execute('SELECT document FROM entries ORDER BY position')]
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError):
        return None


def _assert_owned_cache(database):
    if database.is_symlink():
        raise ValueError(f'Study database must not be a symlink: {database}')
    if not database.exists():
        return
    if not database.is_file():
        raise ValueError(f'Study database must be a regular file: {database}')
    try:
        with database.open('rb') as stream:
            header = stream.read(72)
    except OSError as error:
        raise ValueError(f'Cannot inspect study database {database}: {error}') from error
    owned = (len(header) == 72 and header[:16] == b'SQLite format 3\x00'
             and int.from_bytes(header[68:72], 'big') == APPLICATION_ID)
    if not owned:
        raise ValueError(f'Refusing to replace foreign database: {database}')


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rebuild(database, canonical_hash, entries):
    descriptor, temporary = tempfile.mkstemp(prefix='.study.', suffix='.sqlite3',
                                             dir=database.parent)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.execute(f'PRAGMA application_id={APPLICATION_ID}')
            db.executescript('''
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE entries (
                    position INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL, document TEXT NOT NULL
                );
            ''')
            db.execute('PRAGMA user_version=1')
            db.execute('INSERT INTO metadata VALUES(?,?)', ('canonical_hash', canonical_hash))
            db.executemany('INSERT INTO entries VALUES(?,?,?,?)', [
                (position, entry['id'], entry['kind'],
                 json.dumps(entry, ensure_ascii=False, sort_keys=True))
                for position, entry in enumerate(entries)
            ])
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('materialized study database failed integrity check')
        os.chmod(temporary, 0o600)
        os.replace(temporary, database)
        _sync_directory(database.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_entries(assets, database=None):
    """Return the ordered catalog, rebuilding its SQLite cache when sources change."""
    assets = Path(assets)
    database = _database_path(database)
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_owned_cache(database)
    lock_path = database.with_name(database.name + '.lock')
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _assert_owned_cache(database)
        canonical_hash, sources = _canonical_sources(assets)
        cached = _read_cache(database, canonical_hash)
        if cached is not None:
            return cached
        entries = _catalog(assets, sources)
        _assert_owned_cache(database)
        _rebuild(database, canonical_hash, entries)
        return entries


def _write_immutable(path, entry):
    content = (json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.stem + '.', suffix='.tmp',
                                             dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FileExistsError(f'Study entry {entry["id"]} is immutable') from error
        _sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_entry(assets, entry, database=None, track=True):
    """Save one immutable canonical entry, rebuild the cache, and stage that file."""
    assets = Path(assets).resolve()
    _validate_entry(entry)
    directory = assets / 'study/entries'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f'{entry["id"]}.json'
    _write_immutable(path, entry)
    load_entries(assets, database)
    if track:
        checkout = assets.parents[2]
        relative = path.relative_to(checkout)
        try:
            subprocess.run(['fossil', 'add', str(relative)], cwd=checkout, check=True,
                           capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as error:
            detail = getattr(error, 'stderr', '') or str(error)
            raise RuntimeError(f'Entry saved at {path}, but Fossil staging failed: '
                               f'{detail.strip()}') from error
    return path
