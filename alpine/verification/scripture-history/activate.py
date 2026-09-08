#!/usr/bin/env python3
"""Back up personal Scripture data and replace only its owned desktop helpers."""
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[3]
STATE = Path.home() / '.local/state/oldbook'
EVIDENCE = Path(__file__).resolve().parent
BAR = REPO / 'alpine/desktop/.local/bin/oldbook-scripture-bar'
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-scripture'
SOURCE_PATHS = [BAR, HELPER, REPO / 'alpine/desktop/.local/lib/oldbook/scripture_history.py',
                REPO / 'alpine/desktop/.local/lib/oldbook/scripture_history_reader.py',
                REPO / 'alpine/desktop/.local/lib/oldbook/conky_policy.py',
                REPO / 'alpine/desktop/.config/conky/panels.json']


def arguments(pid):
    return [os.fsdecode(value) for value in (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0') if value]


def bars():
    result = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid == os.getuid() and any(Path(value).name == 'oldbook-scripture-bar' for value in arguments(int(proc.name))):
                result.append(int(proc.name))
        except (OSError, ValueError):
            pass
    return result


def alive(pid):
    try:
        return (Path('/proc') / str(pid) / 'stat').read_text().split()[2] != 'Z'
    except OSError:
        return False


def database_status(path):
    with closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True)) as db:
        return {'integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
                'entries': db.execute('SELECT count(*) FROM entries').fetchone()[0],
                'additions': db.execute('SELECT count(*) FROM additions').fetchone()[0],
                'current_id': db.execute('SELECT entry_id FROM current').fetchone()[0],
                'next_at': db.execute('SELECT next_at FROM current').fetchone()[0]}


def main():
    old = int((STATE / 'scripture/bar.pid').read_text())
    descriptor = os.pidfd_open(old)
    proc = Path('/proc') / str(old)
    original = arguments(old)
    if proc.stat().st_uid != os.getuid() or not any(Path(value).name == 'oldbook-scripture-bar' for value in original):
        raise RuntimeError('Scripture bar identity changed')
    if bars() != [old]:
        raise RuntimeError('Expected exactly one existing Scripture bar')
    inherited = dict(item.split(b'=', 1) for item in (proc / 'environ').read_bytes().split(b'\0') if b'=' in item)
    names = ('HOME', 'PATH', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'XDG_RUNTIME_DIR',
             'WAYLAND_DISPLAY', 'SWAYSOCK', 'DBUS_SESSION_BUS_ADDRESS', 'DISPLAY',
             'XDG_CURRENT_DESKTOP', 'XDG_SESSION_TYPE', 'XDG_SESSION_DESKTOP', 'XDG_CONFIG_HOME',
             'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME', 'GTK_THEME', 'GDK_BACKEND')
    environment = {name: os.fsdecode(inherited[os.fsencode(name)]) for name in names if os.fsencode(name) in inherited}
    if not environment.get('WAYLAND_DISPLAY') or not environment.get('XDG_RUNTIME_DIR'):
        raise RuntimeError('Existing bar lacks its Wayland environment')
    data = Path(environment.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'oldbook/scripture'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = STATE / 'backups' / ('scripture-hourly-activation-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    shutil.copytree(STATE / 'scripture', backup / 'state', symlinks=True)
    manifests = {}
    for name in ('history.sqlite3', 'study.sqlite3'):
        source = data / name
        if not source.is_file():
            continue
        destination = backup / name
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(f'file:{source}?mode=ro', uri=True)) as source_db, closing(sqlite3.connect(destination)) as target_db:
            source_db.backup(target_db)
            assert target_db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        manifests[name] = {'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'integrity': 'ok'}
    (backup / 'manifest.json').write_text(json.dumps({'note': 'Before explicit activation. The existing linked periodic helper had already initialized history; earlier backup also retained.', 'databases': manifests}, indent=2) + '\n')
    before = database_status(data / 'history.sqlite3')
    conky = STATE / 'conky'
    pids_before = json.loads((conky / 'pids.json').read_text())
    (backup / 'activation-before.json').write_text(json.dumps({'bar_pid': old, 'conky': pids_before,
                                                              'database': before}, indent=2) + '\n')
    with (conky / 'layout.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = conky / 'scripture.conf'
        text = config.read_text()
        shutil.copy2(config, backup / 'scripture.conf')
        adjusted, count = re.subn(r'(\$\{execpi\s+)\d+(\s+[^}\n]*oldbook-scripture\s+panel\b)', r'\g<1>3600\2', text)
        if count != 1:
            raise RuntimeError('Expected one Scripture panel command')
        if adjusted != text:
            temporary = config.with_name('scripture.conf.activation.tmp')
            temporary.write_text(adjusted)
            temporary.replace(config)
    # Refresh this card only; other panels retain their processes and geometry.
    for attempt in range(3):
        result = subprocess.run([str(HELPER), 'refresh', 'scripture'], env=environment,
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            break
    if result.returncode:
        raise RuntimeError('Scripture card refresh failed; existing bar was retained')
    signal.pidfd_send_signal(descriptor, signal.SIGTERM)
    if not select.select([descriptor], [], [], 3)[0]:
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        if not select.select([descriptor], [], [], 2)[0]:
            raise RuntimeError('Previous Scripture bar did not exit')
    os.close(descriptor)
    with (STATE / 'scripture/bar.log').open('ab') as log:
        for attempt in range(3):
            replacement = subprocess.Popen(['/usr/bin/python3', str(BAR)], env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            time.sleep(2)
            if replacement.poll() is None:
                break
        if replacement.poll() is not None:
            raise RuntimeError('Scripture bar failed three launch attempts; inspect its private log')
    deadline = time.monotonic() + 12
    while True:
        new = int((STATE / 'scripture/bar.pid').read_text())
        if new == replacement.pid and bars() == [new]:
            break
        if replacement.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError('Replacement Scripture bar singleton check failed')
        time.sleep(.25)
    pids_after = json.loads((conky / 'pids.json').read_text())
    others_unchanged = {name: pid for name, pid in pids_before.items() if name != 'scripture'} == {name: pid for name, pid in pids_after.items() if name != 'scripture'}
    if not others_unchanged or not all(alive(pid) for pid in pids_after.values()):
        raise RuntimeError('Conky process verification failed')
    after = database_status(data / 'history.sqlite3')
    rendered = int((STATE / 'scripture/panel-entry').read_text())
    assert rendered == after['current_id']
    assert after['entries'] >= before['entries'] and after['additions'] == before['additions']
    record = {'status': 'passed', 'backup': str(backup), 'bar_before': old, 'bar_after': new,
              'singleton': bars(), 'conky_before': pids_before, 'conky_after': pids_after,
              'other_conky_processes_unchanged': others_unchanged, 'scripture_execpi_seconds': 3600,
              'saved_deadline_check_seconds': 60, 'rendered_current_id_matches': True,
              'database_before': before, 'database_after': after,
              'source_sha256': {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCE_PATHS},
              'desktop_interaction': 'No windows were opened or focused; only Scripture card and Scripture bar restarted.',
              'limitations': 'Hourly boundary verified with controlled clocks; no physical one-hour wait. Native reader screenshots use synthetic private-session content.'}
    (EVIDENCE / 'activation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
