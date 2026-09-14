"""What you are actually looking at, past whatever the window title claims.

A title says whatever the program felt like saying. "~" does not tell you
whether that is Foot or Ghostty, whether tmux is in the way, or what is running
inside it. This reads the process tree behind the focused window and names the
chain the way you would say it aloud — ghostty › tmux › nvim — with the
directory that program is sitting in, the repository it belongs to and what is
open beside it.

Three rules run through all of it. Nothing here may block the caption: a /proc
entry that vanished between two reads, a program that exited mid-walk or a
repository that will not answer simply drops out of the line rather than
raising, and anything that costs a process runs on a worker thread while the
caption keeps the last answer it had. Nothing here may cost much: the chain is
plain /proc reads, git's branch is one small file, Fossil's is a SQLite read
rather than a fork, and the answers are cached against the thing that produced
them. And whatever does cost something is on the power ladder like every other
expense on this desktop, so a battery sheds it.
"""
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
from xml.sax.saxutils import escape, quoteattr

import power_source

PROC = Path(os.environ.get('OLDBOOK_PROC_ROOT', '/proc'))
# A shell is scaffolding: it is worth naming only when nothing runs inside it.
SHELLS = frozenset({'sh', 'bash', 'zsh', 'dash', 'fish', 'ash', 'ksh', 'busybox'})
MULTIPLEXERS = frozenset({'tmux', 'tmux: client', 'screen', 'zellij', 'dtach', 'abduco'})
DEPTH = 12
TTL = 2.0
DETAIL_TTL = 4.0
STATUS_TTL = 8.0
NAME_LIMIT = 14
TAB_LIMIT = 4

# JetBrainsMono Nerd Font, and only from ranges the font has carried for years:
# Devicons for the two repository kinds and Font Awesome for everything else, so
# a caption never falls back to a replacement box for want of a fashionable
# codepoint.
GLYPHS = {
    'git': '',       # the git logo
    'fossil': '',    # a database: Fossil is one file, and says so
    'branch': '',    # the branch fork
    'dirty': '',     # a filled dot: uncommitted work
    'clean': '',     # a check: nothing to commit
    'ahead': '',     # arrow up: committed here, not sent
    'behind': '',    # arrow down: waiting in the repository
    'tabs': '',      # stacked pages: more of the same window
}
# Rounded, the same separator the prompt and the status bars wear, so the
# strip reads as one more chain of the same family. Written as an escape:
# a tool that drops private-use characters once emptied the prompt's slots.
POWERLINE = '\ue0b4'
CHAIN = ' › '
SEPARATOR = ' · '
# What the caption gives up first as the strip narrows, in order. The workspace
# identity and the program you are in are never on this list: they are the two
# things the caption exists to answer.
SHEDDING = ('tab_names', 'tabs', 'status', 'branch', 'directory', 'place')
# One ground per segment, alternating so neighbours always differ, and never a
# colour chosen by eye: every one is a role the active theme declares.
ROLE_COLORS = {
    'workspace': ('accent', 'background_hard'),
    'chain': ('surface', 'foreground'),
    'place': ('background_hard', 'foreground'),
    'tabs': ('surface', 'muted'),
    # An agent's own state glyph (agent_status.WAITING/WORKING): the one
    # segment meant to catch the eye, since it names the one thing on this
    # strip that might actually need a reply.
    'agent': ('accent', 'background_hard'),
}

_CACHE = {}
_DETAIL = {}
_FACTS = {}
_STATUS = {}
_PENDING = set()
_LOCK = threading.Lock()


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


def tmux_query(*arguments):
    try:
        found = subprocess.run(['tmux', *arguments], capture_output=True, text=True, timeout=2)
        return found.stdout if found.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def tmux_session(client):
    """Which session this client is attached to; everything else follows from it."""
    for line in tmux_query('list-clients', '-F', '#{client_pid}|#{session_name}').splitlines():
        found = line.split('|', 1)
        if len(found) == 2 and found[0] == str(client):
            return found[1]
    return None


def tmux_pane(client, session=None):
    """Ask tmux, because the pane's program is a child of the server, not of us.

    The client process in our chain never parents the program in the pane, so
    walking /proc alone stops at "tmux" and calls it a day.
    """
    session = tmux_session(client) if session is None else session
    if session is None:
        return None
    command, _, path = tmux_query(
        'display-message', '-p', '-t', session, '-F',
        '#{pane_current_command}|#{pane_current_path}').strip().partition('|')
    return (command, path) if command else None


def tmux_tabs(client, session=None):
    """tmux windows are real tabs: it already keeps the list, so ask for it.

    This is the only tab set a compositor can honestly show. Wayland gives no
    program the titles inside another program's window, so a browser's or a
    file manager's tabs are unreachable and are not guessed at here.
    """
    session = tmux_session(client) if session is None else session
    if session is None:
        return None
    names, index = [], 0
    for line in tmux_query('list-windows', '-t', session, '-F',
                           '#{window_index}|#{window_name}|#{window_active}').splitlines():
        found = line.split('|')
        if len(found) != 3:
            continue
        names.append(found[1].strip() or found[0])
        if found[2] == '1':
            index = len(names)
    if len(names) < 2:
        return None
    return {'source': 'tmux', 'index': index, 'count': len(names), 'names': names}


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


def git_head(path):
    """The branch from git's own HEAD file: one small read, no process at all."""
    head = path / '.git/HEAD'
    if not head.is_file():
        # A worktree or submodule keeps a `.git` file pointing at the real one.
        pointer = path / '.git'
        try:
            if not pointer.is_file():
                return None
            target = pointer.read_text().strip()
            if not target.startswith('gitdir:'):
                return None
            head = Path(target.split(':', 1)[1].strip()) / 'HEAD'
            if not head.is_absolute():
                head = path / head
        except OSError:
            return None
    try:
        text = head.read_text().strip()
    except OSError:
        return None
    return text.rsplit('/', 1)[-1] if text.startswith('ref:') else text[:9] or None


def fossil_reader(path):
    """Open one of Fossil's SQLite files read-only, or give up quietly."""
    return sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=0.2)


def fossil_facts(root):
    """Branch and standing, read straight out of Fossil's two SQLite files.

    Fossil keeps everything in SQLite: the checkout names its repository and the
    check-in it is sitting on, and the repository holds the branch tags, the
    leaves and the artifacts a sync has not sent yet. The standard library reads
    all of that in a few milliseconds where `fossil branch current` costs a
    fork, an exec and a lock on the repository the user may be committing to.
    Anything unexpected — a newer schema, a busy database, a repository that has
    moved — drops the answer instead of raising.
    """
    facts = {'branch': None, 'ahead': None, 'behind': None}
    checkout = next((name for name in ('.fslckout', '_FOSSIL_')
                     if (Path(root) / name).exists()), None)
    if checkout is None:
        return facts
    try:
        with fossil_reader(Path(root) / checkout) as local:
            values = dict(local.execute(
                "SELECT name, value FROM vvar WHERE name IN ('checkout', 'repository')").fetchall())
        rid = int(values['checkout'])
        with fossil_reader(values['repository']) as repository:
            tag = repository.execute("SELECT tagid FROM tag WHERE tagname='branch'").fetchone()
            if tag is None:
                return facts
            branch = repository.execute(
                'SELECT value FROM tagxref WHERE rid=? AND tagid=?', (rid, tag[0])).fetchone()
            facts['branch'] = branch[0] if branch and branch[0] else None
            moment = repository.execute(
                "SELECT mtime FROM event WHERE objid=? AND type='ci'", (rid,)).fetchone()
            if facts['branch'] and moment:
                behind = repository.execute(
                    'SELECT count(*) FROM event JOIN tagxref ON tagxref.rid = event.objid '
                    "WHERE event.type='ci' AND event.mtime > ? AND tagxref.tagid = ? "
                    'AND tagxref.value = ?', (moment[0], tag[0], facts['branch'])).fetchone()
                facts['behind'] = int(behind[0]) if behind else None
            # Unsent artifacts only mean "ahead" where there is somewhere to
            # send them; a repository that has never synced is not behind hand.
            remote = repository.execute(
                "SELECT count(*) FROM config WHERE name='last-sync-url'").fetchone()
            if remote and remote[0]:
                ahead = repository.execute(
                    'SELECT count(*) FROM unsent JOIN event ON event.objid = unsent.rid '
                    "AND event.type='ci'").fetchone()
                facts['ahead'] = int(ahead[0]) if ahead else None
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError):
        return {'branch': None, 'ahead': None, 'behind': None}
    return facts


def read_facts(root):
    """The branch, from SQLite if the schema answers and from Fossil if not."""
    facts = fossil_facts(root)
    if facts['branch']:
        return facts
    try:
        answer = subprocess.run(['fossil', 'branch', 'current'], cwd=str(root),
                                capture_output=True, text=True, timeout=6)
        return dict(facts, branch=answer.stdout.strip() or None)
    except (OSError, subprocess.SubprocessError):
        return facts


def refresh_facts(root):
    """Read Fossil's answers on a worker; ten milliseconds is a dropped frame."""
    facts = read_facts(root)
    with _LOCK:
        _FACTS[root] = (time.monotonic(), facts)
        _PENDING.discard(('facts', root))
        trim(_FACTS)
    return facts


def fossil_branch(root, current=None, blocking=False):
    """The branch this checkout is on, from cache.

    Reading it is milliseconds rather than a fork, but the caption is drawn on
    the compositor's own thread and a frame is sixteen milliseconds, so even
    this happens on a worker and the strip shows the last answer meanwhile.
    """
    root = str(root)
    with _LOCK:
        cached = _FACTS.get(root)
    if cached and time.monotonic() - cached[0] < status_interval(current):
        return cached[1].get('branch')
    if blocking:
        return refresh_facts(root).get('branch')
    schedule(('facts', root), refresh_facts, root)
    return cached[1].get('branch') if cached else None


def allowed(current=None):
    """The one ladder entry the whole of this module's expense sits on."""
    return power_source.allows('window-context-detail', current)


def status_interval(current=None):
    """Ask a repository less often on a battery: this answer costs a process."""
    return STATUS_TTL if (current or power_source.posture()) == 'mains' else STATUS_TTL * 4


def repository(directory, current=None, blocking=False):
    """Which repository this directory belongs to, and what it is called.

    Git answers from a file, so it answers on any battery. Fossil has to be
    asked — cheaply now, but still a database read and a possible fork — so it
    stays on the ladder exactly as before: a checkout still names itself when
    the battery is low, it just stops saying which branch.
    """
    path = Path(directory) if directory else None
    while path is not None and path != path.parent:
        try:
            head = git_head(path)
        except OSError:
            return None
        if head is not None:
            return {'kind': 'git', 'root': str(path), 'branch': head}
        if (path / '.fslckout').exists() or (path / '_FOSSIL_').exists():
            return {'kind': 'fossil', 'root': str(path),
                    'branch': (fossil_branch(path, current, blocking)
                               if allowed(current) else None)}
        path = path.parent
    return None


def branch(directory):
    """The branch alone, kept for callers that only ever wanted the name."""
    found = repository(directory)
    return found['branch'] if found else None


def git_status(root):
    """Dirty, ahead and behind in one call, which is why porcelain v2 is used."""
    found = subprocess.run(
        ['git', 'status', '--porcelain=v2', '--branch', '--untracked-files=no'],
        cwd=root, capture_output=True, text=True, timeout=6)
    if found.returncode != 0:
        return {}
    record = {'dirty': False, 'ahead': None, 'behind': None}
    for line in found.stdout.splitlines():
        if line.startswith('# branch.ab '):
            counts = line.split()[2:]
            for value in counts:
                try:
                    if value.startswith('+'):
                        record['ahead'] = int(value[1:])
                    elif value.startswith('-'):
                        record['behind'] = int(value[1:])
                except ValueError:
                    continue
        elif line and not line.startswith('#'):
            record['dirty'] = True
    return record


def fossil_status(root):
    """Fossil's dirty flag needs the program; its standing does not.

    `fossil changes` walks the tracked files, which is the only honest way to
    know whether the checkout has been edited. Ahead and behind come from the
    repository database instead, where they are two indexed counts.
    """
    record = dict(refresh_facts(root))
    record.pop('branch', None)
    found = subprocess.run(['fossil', 'changes'], cwd=root,
                           capture_output=True, text=True, timeout=6)
    if found.returncode != 0:
        return record
    record['dirty'] = bool(found.stdout.strip())
    return record


def refresh_status(kind, root):
    """Run the expensive half on a worker; the caption never waits for it."""
    try:
        record = git_status(root) if kind == 'git' else fossil_status(root)
    except (OSError, subprocess.SubprocessError, sqlite3.Error, ValueError):
        record = {}
    with _LOCK:
        _STATUS[root] = (time.monotonic(), record)
        _PENDING.discard(('status', root))
        trim(_STATUS)


def schedule(key, target, *arguments):
    """One worker per outstanding question, and never a second for the same one."""
    with _LOCK:
        if key in _PENDING:
            return
        _PENDING.add(key)
    threading.Thread(target=target, args=arguments, daemon=True).start()


def status(found, blocking=False, current=None):
    """What the repository is doing, from cache, refreshed behind the caption.

    Dirty state costs a process on both systems, so it is on the ladder and it
    is never computed on the thread that draws: the caption shows the last
    answer while a worker fetches the next one. A battery low enough to shed
    the ladder shows the branch and stops there.
    """
    if not found or not found.get('root'):
        return {}
    if not allowed(current):
        return {}
    root = found['root']
    with _LOCK:
        cached = _STATUS.get(root)
    if cached and time.monotonic() - cached[0] < status_interval(current):
        return dict(cached[1])
    if blocking:
        refresh_status(found.get('kind'), root)
        with _LOCK:
            cached = _STATUS.get(root)
        return dict(cached[1]) if cached else {}
    schedule(('status', root), refresh_status, found.get('kind'), root)
    return dict(cached[1]) if cached else {}


def refresh_detail(pid, client):
    """The tmux half: the pane's program, its directory and the window list."""
    record = {}
    try:
        session = tmux_session(client)
        if session is not None:
            pane = tmux_pane(client, session)
            if pane:
                record['pane'] = pane
            tabs = tmux_tabs(client, session)
            if tabs:
                record['tabs'] = tabs
    except (OSError, subprocess.SubprocessError):
        record = {}
    with _LOCK:
        _DETAIL[pid] = (time.monotonic(), record)
        _PENDING.discard(('detail', pid))
        trim(_DETAIL)


def detail(pid, client, blocking=False, current=None):
    """Everything tmux knows, cached against the window that asked."""
    if not allowed(current):
        return {}
    with _LOCK:
        cached = _DETAIL.get(pid)
    if cached and time.monotonic() - cached[0] < DETAIL_TTL:
        return cached[1]
    if blocking:
        refresh_detail(pid, client)
        with _LOCK:
            cached = _DETAIL.get(pid)
        return cached[1] if cached else {}
    schedule(('detail', pid), refresh_detail, pid, client)
    return cached[1] if cached else {}


def shorten(directory, home=None):
    home = str(Path.home()) if home is None else home
    if directory == home:
        return '~'
    return '~' + directory[len(home):] if directory.startswith(home + '/') else directory


def trim(cache, limit=64):
    if len(cache) > limit:
        for stale in sorted(cache, key=lambda key: cache[key][0])[:limit // 2]:
            cache.pop(stale, None)


def describe(pid, terminal=True, blocking=False):
    """The chain, the directory, the repository and the tabs behind one window.

    Only terminals get walked. Everything else already says what it is through
    its icon and its own title, and descending a browser reaches a content
    process that is neither the program the user is looking at nor anywhere
    they have been.
    """
    if not pid or not terminal:
        return {}
    pid = int(pid)
    cached = _CACHE.get(pid)
    if cached and time.monotonic() - cached[0] < TTL:
        return cached[1]
    # One reading of the power posture for every question this record asks.
    current = power_source.posture()
    line = descend(pid)
    names = [comm(entry) for entry in line]
    directory = working_directory(line[-1]) or working_directory(line[0])
    tabs = None
    for index, name in enumerate(names):
        if name in MULTIPLEXERS:
            found = detail(pid, line[index], blocking, current)
            pane = found.get('pane')
            if pane:
                names = names[:index + 1] + [pane[0]]
                directory = pane[1] or directory
            tabs = found.get('tabs')
            break
    found = repository(directory, current, blocking)
    record = {'chain': readable(names), 'directory': shorten(directory) if directory else '',
              'branch': found['branch'] if found else None, 'tabs': tabs,
              'repository': dict(found, **status(found, blocking, current)) if found else None}
    _CACHE[pid] = (time.monotonic(), record)
    trim(_CACHE)
    return record


def workspace_label(name):
    """"10: Strata . window hint" is three things; the strip wants the first two."""
    number, separator, rest = str(name or '').partition(':')
    identity = (rest if separator else number).split('·')[0].strip()
    number = number.strip() if separator and number.strip().isdigit() else ''
    return ' '.join(part for part in (number, identity) if part)


def repository_text(found, branch_name=True, detail_glyphs=True):
    """The repository as glyphs: which system, which branch, how it stands.

    Kind first, because git and Fossil are not interchangeable and the strip is
    often the only place that says which one you are in. Then the branch, then
    the standing — a dot for uncommitted work, arrows for what has not moved
    between here and the remote. A repository with nothing to report shows a
    check rather than a blank, so "clean" is a statement instead of a silence.
    """
    if not found:
        return ''
    parts = [GLYPHS.get(found.get('kind'), '')]
    if branch_name and found.get('branch'):
        parts.append(GLYPHS['branch'] + ' ' + found['branch'])
    if detail_glyphs:
        marks = []
        if found.get('dirty'):
            marks.append(GLYPHS['dirty'])
        for name in ('ahead', 'behind'):
            count = found.get(name)
            if isinstance(count, int) and count > 0:
                marks.append(GLYPHS[name] + str(count))
        if not marks and found.get('dirty') is False:
            marks.append(GLYPHS['clean'])
        parts.extend(marks)
    return ' '.join(part for part in parts if part)


def shorten_name(value, limit=NAME_LIMIT):
    """A tab name is a hint, not a title: enough to recognise, never a sentence."""
    value = ' '.join(str(value).split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def tab_text(tabs, names=True):
    """Where you are in the set, and — while there is room — what else is in it.

    The active tab is left out of the list on purpose: the caption has already
    said what is running in it, and repeating the name costs the space the
    other tabs need.
    """
    if not tabs:
        return ''
    count = tabs.get('count') or 0
    if count < 2:
        return ''
    index = tabs.get('index') or 0
    text = f"{GLYPHS['tabs']} {index}/{count}"
    if not names:
        return text
    others = [shorten_name(name) for position, name in enumerate(tabs.get('names') or [], 1)
              if position != index and str(name).strip()]
    if not others:
        return text
    shown = others[:TAB_LIMIT]
    if len(others) > TAB_LIMIT:
        shown.append('…')
    return text + ' ' + ', '.join(shown)


def assemble(record, workspace='', detail_shown=None):
    """One list of (role, text) segments, in the order they are read aloud."""
    shown = {name: True for name in
             ('tab_names', 'tabs', 'status', 'branch', 'directory', 'place')}
    shown.update(detail_shown or {})
    parts = []
    if workspace:
        parts.append(('workspace', workspace))
    chain = record.get('chain') or []
    if chain:
        parts.append(('chain', CHAIN.join(chain)))
    elif record.get('title'):
        parts.append(('chain', record['title']))
    place = []
    directory = record.get('directory')
    if directory and shown['directory']:
        place.append(directory)
    found = record.get('repository')
    if found:
        text = repository_text(found, branch_name=shown['branch'], detail_glyphs=shown['status'])
        if text:
            place.append(text)
    elif directory and shown['directory'] and record.get('branch') and shown['branch']:
        place.append(GLYPHS['branch'] + ' ' + record['branch'])
    if place and shown['place']:
        parts.append(('place', ' '.join(place)))
    if shown['tabs']:
        tabs = tab_text(record.get('tabs'), names=shown['tab_names'])
        if tabs:
            parts.append(('tabs', tabs))
    return parts


def segments(record, workspace='', budget=None):
    """The caption, narrowed until it fits, giving up the least useful part first.

    Ellipsis at the end of a label cuts whatever happens to be last, which is a
    poor way to decide what a person loses. The strip drops whole ideas instead
    and in a fixed order: the other tabs' names, then the tab count, then how
    the repository stands, then which branch, then the directory. What survives
    every narrowing is where you are and what you are in.
    """
    hidden = {}
    parts = assemble(record, workspace, hidden)
    if budget is None:
        return parts
    for name in SHEDDING:
        if len(SEPARATOR.join(text for _, text in parts)) <= budget:
            return parts
        hidden[name] = False
        parts = assemble(record, workspace, hidden)
    return parts


def caption(record, workspace='', budget=None):
    """One line: where you are, what is running, where it is running, what else."""
    return SEPARATOR.join(text for _, text in segments(record, workspace, budget))


def markup(parts, palette, font=None):
    """Powerline as plain text: one ground per segment, one arrow between them.

    A separator drawn in the colour it is leaving over the colour it is entering
    is the whole trick, and it is still a single Pango layout, so the strip pays
    nothing for it beyond parsing the attributes. It is a setting rather than
    the default because it only reads well while neighbouring grounds keep their
    contrast, and a generated theme cannot promise that.

    The chain opens with the first ground and closes into nothing, the way the
    prompt's and the status bars' chains do. The glyph itself is set in `font`
    where one is given: the caption's own face may carry a private-use glyph of
    its own at that codepoint -- Inter does, a subscript digit -- and Pango
    would take that over a fallback that has the real shape.
    """
    palette = palette or {}

    def color(role, index):
        names = ROLE_COLORS.get(role, ROLE_COLORS['chain'])
        return palette.get(names[index], palette.get('foreground', '#ffffff'))

    def separator(ground, following=None):
        attributes = ' foreground=' + quoteattr(ground)
        if following:
            attributes += ' background=' + quoteattr(following)
        if font:
            attributes += ' font_family=' + quoteattr(font)
        return '<span{}>{}</span>'.format(attributes, POWERLINE)

    if not parts:
        return ''
    pieces = [separator(color(parts[0][0], 0))]
    for position, (role, text) in enumerate(parts):
        ground, ink = color(role, 0), color(role, 1)
        pieces.append('<span background={} foreground={}> {} </span>'.format(
            quoteattr(ground), quoteattr(ink), escape(text)))
        following = parts[position + 1][0] if position + 1 < len(parts) else None
        pieces.append(separator(ground, color(following, 0) if following else None))
    return ''.join(pieces)


def reference_markup(reference, font=None):
    """A measuring line as the strip will really draw it: separators in their face."""
    glyph = ('<span font_family={}>{}</span>'.format(quoteattr(font), POWERLINE)
             if font else POWERLINE)
    return escape(reference).replace(POWERLINE, glyph)


def strip_segments(record, budget=None):
    """The strip's own line: the process chain where there is one, the title where not.

    A terminal's own title is usually the directory or nothing at all, so where
    the process chain has something to say it says it instead. Every other
    window keeps the title it chose; the raw title stays in the tooltip either
    way, so nothing that was readable before stops being reachable. Sway's own
    tabbed containers are a real tab set and are shown for any window, while a
    terminal's multiplexer speaks for itself.
    """
    workspace = workspace_label(record.get('workspace', ''))
    provenance = dict(record.get('provenance') or {})
    if not provenance.get('tabs') and record.get('tabs'):
        provenance['tabs'] = record['tabs']
    if provenance.get('chain'):
        return segments(provenance, workspace, budget)
    title = record.get('title')
    if not title:
        empty = 'Empty workspace'
        return [('chain', empty), ('workspace', workspace)] if workspace else [('chain', empty)]
    return segments({'title': title, 'tabs': provenance.get('tabs')}, workspace, budget)


def strip_caption(record, budget=None):
    """The one line the strip shows, as plain text."""
    return SEPARATOR.join(text for _, text in strip_segments(record, budget))


def strip_markup(record, palette, budget=None, font=None):
    """The same line as powerline segments, for the strip that asked for them."""
    return markup(strip_segments(record, budget), palette, font)
