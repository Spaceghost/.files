"""What you are actually looking at, past whatever the window title claims.

A title says whatever the program felt like saying. "~" does not tell you
whether that is Foot or Ghostty, whether tmux is in the way, or what is running
inside it. This reads the process tree behind the focused window and names the
chain the way you would say it aloud — ghostty › tmux › nvim — with the
directory that program is sitting in and the branch it is on.

Two rules run through all of it. Nothing here may block the caption: a /proc
entry that vanished between two reads, a program that exited mid-walk or a
repository that will not answer simply drops out of the line rather than
raising. And nothing here may cost much: the chain is plain /proc reads, the
answers are cached against the process that produced them, and the parts that
need to run a program are on the power ladder like every other expense.
"""
import os
from pathlib import Path
import subprocess
import time

import power_source

PROC = Path(os.environ.get('OLDBOOK_PROC_ROOT', '/proc'))
# A shell is scaffolding: it is worth naming only when nothing runs inside it.
SHELLS = frozenset({'sh', 'bash', 'zsh', 'dash', 'fish', 'ash', 'ksh', 'busybox'})
MULTIPLEXERS = frozenset({'tmux', 'tmux: client', 'screen', 'zellij', 'dtach', 'abduco'})
DEPTH = 12
TTL = 2.0
_CACHE = {}


def comm(pid):
    try:
        return (PROC / str(pid) / 'comm').read_text().strip()
    except OSError:
        return ''


def children(pid):
    """Direct children, from the file the kernel already keeps for the purpose."""
    found = []
    try:
        for task in (PROC / str(pid) / 'task').iterdir():
            try:
                found.extend(int(value) for value in (task / 'children').read_text().split())
            except (OSError, ValueError):
                continue
    except OSError:
        return []
    return found


def descend(pid):
    """Follow one line of descent to the process actually in the foreground.

    Where a process has forked several children the youngest is the one the
    user just started, which is the one worth naming; a helper a terminal
    keeps alive in the background is not what they are looking at.
    """
    line, seen = [pid], {pid}
    for _ in range(DEPTH):
        following = [child for child in children(line[-1]) if child not in seen]
        if not following:
            break
        chosen = max(following)
        seen.add(chosen)
        line.append(chosen)
    return line


def readable(names):
    """Drop the scaffolding, keep the story: shells only when they are the end."""
    # tmux names its client process "tmux: client"; nobody says that out loud.
    spoken = [name.split(':', 1)[0].strip() if name.startswith('tmux:') else name
              for name in names]
    kept = [name for name in spoken if name and name not in SHELLS]
    return kept or ([spoken[-1]] if spoken else [])


def tmux_pane(client):
    """Ask tmux, because the pane's program is a child of the server, not of us.

    The client process in our chain never parents the program in the pane, so
    walking /proc alone stops at "tmux" and calls it a day.
    """
    try:
        clients = subprocess.run(['tmux', 'list-clients', '-F', '#{client_pid}|#{session_name}'],
                                 capture_output=True, text=True, timeout=2)
        session = next((line.split('|', 1)[1] for line in clients.stdout.splitlines()
                        if line.split('|', 1)[0] == str(client)), None)
        if session is None:
            return None
        pane = subprocess.run(['tmux', 'display-message', '-p', '-t', session, '-F',
                               '#{pane_current_command}|#{pane_current_path}'],
                              capture_output=True, text=True, timeout=2)
        command, _, path = pane.stdout.strip().partition('|')
        return (command, path) if command else None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def working_directory(pid):
    """The process's directory, when it is one a person could have chosen.

    A browser's content process answers this with somewhere inside /proc, which
    is true and useless. Anything that is not a real absolute directory outside
    the kernel's own filesystems is no answer at all.
    """
    try:
        found = os.readlink(PROC / str(pid) / 'cwd')
    except OSError:
        return ''
    if not found.startswith('/') or found.startswith(('/proc/', '/sys/')):
        return ''
    try:
        return found if Path(found).is_dir() else ''
    except OSError:
        return ''


def branch(directory):
    """The branch, from the cheapest source that knows it.

    Git's HEAD is a single small read. Fossil has to be asked, so it is on the
    ladder: a checkout still names itself on battery, it just stops saying
    which branch.
    """
    path = Path(directory) if directory else None
    while path is not None and path != path.parent:
        head = path / '.git/HEAD'
        try:
            if head.is_file():
                text = head.read_text().strip()
                return text.rsplit('/', 1)[-1] if text.startswith('ref:') else text[:9]
        except OSError:
            return None
        if (path / '.fslckout').exists() or (path / '_FOSSIL_').exists():
            if not power_source.allows('window-context-detail'):
                return None
            try:
                found = subprocess.run(['fossil', 'branch', 'current'], cwd=str(path),
                                       capture_output=True, text=True, timeout=2)
                return found.stdout.strip() or None
            except (OSError, subprocess.SubprocessError):
                return None
        path = path.parent
    return None


def shorten(directory, home=None):
    home = str(Path.home()) if home is None else home
    if directory == home:
        return '~'
    return '~' + directory[len(home):] if directory.startswith(home + '/') else directory


def describe(pid, terminal=True):
    """The chain, the directory and the branch behind one window.

    Only terminals get walked. Everything else already says what it is through
    its icon and its own title, and descending a browser reaches a content
    process that is neither the program the user is looking at nor anywhere
    they have been.
    """
    if not pid or not terminal:
        return {}
    cached = _CACHE.get(pid)
    if cached and time.monotonic() - cached[0] < TTL:
        return cached[1]
    line = descend(int(pid))
    names = [comm(entry) for entry in line]
    directory = working_directory(line[-1]) or working_directory(line[0])
    detail = power_source.allows('window-context-detail')
    for index, name in enumerate(names):
        if name in MULTIPLEXERS and detail:
            pane = tmux_pane(line[index])
            if pane:
                names = names[:index + 1] + [pane[0]]
                directory = pane[1] or directory
            break
    record = {'chain': readable(names), 'directory': shorten(directory) if directory else '',
              'branch': branch(directory)}
    _CACHE[pid] = (time.monotonic(), record)
    if len(_CACHE) > 64:
        for stale in sorted(_CACHE, key=lambda key: _CACHE[key][0])[:32]:
            _CACHE.pop(stale, None)
    return record


def workspace_label(name):
    """"10: Strata . window hint" is three things; the strip wants the first two."""
    number, separator, rest = str(name or '').partition(':')
    identity = (rest if separator else number).split('\u00b7')[0].strip()
    number = number.strip() if separator and number.strip().isdigit() else ''
    return ' '.join(part for part in (number, identity) if part)


def caption(record, workspace=''):
    """One line: where you are, what is running, and where it is running."""
    parts = []
    if workspace:
        parts.append(workspace)
    chain = record.get('chain') or []
    if chain:
        parts.append(' › '.join(chain))
    directory = record.get('directory')
    if directory:
        found = record.get('branch')
        parts.append(f'{directory} ({found})' if found else directory)
    return ' · '.join(parts)


def strip_caption(record):
    """The one line the strip shows: where you are, and what you are looking at.

    A terminal's own title is usually the directory or nothing at all, so where
    the process chain has something to say it says it instead. Every other
    window keeps the title it chose; the raw title stays in the tooltip either
    way, so nothing that was readable before stops being reachable.
    """
    workspace = workspace_label(record.get('workspace', ''))
    provenance = record.get('provenance') or {}
    if provenance.get('chain'):
        return caption(provenance, workspace)
    title = record.get('title')
    if not title:
        return f'Empty workspace · {workspace}' if workspace else 'Empty workspace'
    return ' · '.join(part for part in (workspace, title) if part)
