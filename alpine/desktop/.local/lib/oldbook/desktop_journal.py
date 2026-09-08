"""Persistent, deliberately slow rotation of desktop notes and Coast to Coast lines."""
import argparse
from contextlib import closing
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import textwrap
import time

INTERVAL = 240


def open_database(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Journal database must not be a symlink')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    os.chmod(path, 0o600)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    if db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
        db.close()
        raise ValueError('Unsupported journal database version')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('journal','quip')),
            entry_date TEXT NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            enabled INTEGER NOT NULL DEFAULT 1, last_shown REAL,
            UNIQUE(kind, entry_date, body)
        );
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rotation (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), slot INTEGER, entry_id INTEGER
        );
        PRAGMA user_version=1;
    ''')
    return db


def add_entry(db, body, kind, entry_date, source):
    body = body.strip()
    if not body:
        raise ValueError('Entry text must not be empty')
    date.fromisoformat(entry_date)
    with db:
        db.execute('INSERT OR IGNORE INTO entries(kind,entry_date,body,source) VALUES(?,?,?,?)',
                   (kind, entry_date, body, source))
    return db.execute('SELECT id FROM entries WHERE kind=? AND entry_date=? AND body=?',
                      (kind, entry_date, body)).fetchone()[0]


def seed(db, records, legacy):
    # A single transaction keeps two simultaneous Conky starts from importing twice.
    with db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM metadata WHERE key='seed-v1'").fetchone():
            return
        for record in records:
            date.fromisoformat(record['date'])
            db.execute('INSERT OR IGNORE INTO entries(kind,entry_date,body,source) VALUES(?,?,?,?)',
                       (record['kind'], record['date'], record['body'], record['source']))
        for body in legacy:
            if isinstance(body, str) and body.strip():
                exists = db.execute('SELECT 1 FROM entries WHERE body=?', (body.strip(),)).fetchone()
                if not exists:
                    db.execute('INSERT INTO entries(kind,entry_date,body,source) VALUES(?,?,?,?)',
                               ('quip', date.today().isoformat(), body.strip(), 'legacy-panels'))
        db.execute("INSERT INTO metadata VALUES('seed-v1','imported')")


def choose(db, now=None, advance=False):
    now = time.time() if now is None else now
    slot = int(now // INTERVAL)
    with db:
        db.execute('BEGIN IMMEDIATE')
        state = db.execute('SELECT * FROM rotation WHERE singleton=1').fetchone()
        previous = (db.execute('SELECT * FROM entries WHERE id=?', (state['entry_id'],)).fetchone()
                    if state else None)
        if not advance and state and state['slot'] == slot and previous and previous['enabled']:
            return dict(previous)
        counter = db.execute("SELECT value FROM metadata WHERE key='rotation-count'").fetchone()
        count = int(counter[0]) if counter else 0
        # Keep the original Coast to Coast voice dominant: three quips, then a note.
        desired = 'journal' if count % 4 == 3 else 'quip'
        row = db.execute('''SELECT * FROM entries WHERE enabled=1
            ORDER BY (kind=?) DESC, COALESCE(last_shown,0), id LIMIT 1''', (desired,)).fetchone()
        if row is None:
            return None
        db.execute('UPDATE entries SET last_shown=? WHERE id=?', (now, row['id']))
        db.execute('INSERT OR REPLACE INTO rotation VALUES(1,?,?)', (slot, row['id']))
        db.execute("INSERT OR REPLACE INTO metadata VALUES('rotation-count',?)", (str(count + 1),))
        return dict(row)


def render(row):
    if row is None:
        return 'The notebook is quiet. No entries enabled.'
    heading = row['entry_date'] + ' · Journal\n' if row['kind'] == 'journal' else ''
    lines = textwrap.wrap(row['body'], 46)
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1][:43].rstrip() + '…'
    return heading + '\n'.join(lines)


def backup(db, destination):
    destination = Path(destination)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(destination)) as copy:
        db.backup(copy)


def main():
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=data / 'oldbook/journal/entries.sqlite3')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('show', help='print the current four-minute desktop excerpt')
    commands.add_parser('next', help='advance the desktop excerpt immediately')
    commands.add_parser('list', help='print every complete entry as JSON')
    add = commands.add_parser('add', help='save a journal note or a Coast to Coast line')
    add.add_argument('--text', required=True)
    add.add_argument('--kind', choices=('journal', 'quip'), default='journal')
    add.add_argument('--date', default=date.today().isoformat())
    disable = commands.add_parser('disable', help='keep an entry but stop displaying it')
    disable.add_argument('id', type=int)
    copy = commands.add_parser('backup', help='make a consistent SQLite backup')
    copy.add_argument('destination', type=Path)
    args = parser.parse_args()
    with closing(open_database(args.database)) as db:
        if not db.execute("SELECT 1 FROM metadata WHERE key='seed-v1'").fetchone():
            source = Path(__file__).resolve().parents[2] / 'share/oldbook/journal-seed.json'
            legacy_path = Path.home() / '.config/conky/panels.json'
            legacy = json.loads(legacy_path.read_text()).get('ghost_lines', []) if legacy_path.exists() else []
            seed(db, json.loads(source.read_text()), legacy)
        if args.action in ('show', 'next'):
            print(render(choose(db, advance=args.action == 'next')))
        elif args.action == 'list':
            print(json.dumps([dict(row) for row in db.execute('SELECT * FROM entries ORDER BY id')],
                             ensure_ascii=False, indent=2))
        elif args.action == 'add':
            print(add_entry(db, args.text, args.kind, args.date, 'manual'))
        elif args.action == 'disable':
            with db:
                cursor = db.execute('UPDATE entries SET enabled=0 WHERE id=?', (args.id,))
                if not cursor.rowcount:
                    raise ValueError('No entry with that ID')
        elif args.action == 'backup':
            backup(db, args.destination)


if __name__ == '__main__':
    main()
