"""Index desktop applications and rank them for a typed query.

Pure logic: no GTK, no Wayland, no display. The Launchpad overlay renders what
this module returns, and the tests exercise it directly. Desktop entries follow
the freedesktop specification closely enough for a launcher: the first entry
found for a given identifier wins, which is what the XDG search-path precedence
asks for, and hidden or foreign-desktop entries never reach the grid.
"""
import configparser
import os
from pathlib import Path
import re
import shlex

# Field codes the specification defines for Exec. None of them survive into the
# argument list: the launcher opens an application, never a document.
FIELD_CODE = re.compile(r'^%[fFuUdDnNickvm]$')
DESKTOP_NAME = 'sway'


def data_directories(environment=None):
    """The applications directories, highest precedence first."""
    environment = os.environ if environment is None else environment
    home = environment.get('XDG_DATA_HOME') or os.path.join(
        environment.get('HOME', str(Path.home())), '.local/share')
    system = environment.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
    directories = [home] + [part for part in system.split(':') if part]
    seen, result = set(), []
    for directory in directories:
        path = Path(directory) / 'applications'
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _parser():
    parser = configparser.RawConfigParser(strict=False, interpolation=None,
                                          delimiters=('=',), comment_prefixes=('#',))
    parser.optionxform = str
    return parser


def _localized(section, key, locales):
    for locale in locales:
        value = section.get(f'{key}[{locale}]')
        if value:
            return value
    return section.get(key, '')


def locale_candidates(environment=None):
    """Locale names to try for Name and Comment, most specific first."""
    environment = os.environ if environment is None else environment
    value = (environment.get('LC_MESSAGES') or environment.get('LC_ALL')
             or environment.get('LANG') or '')
    value = value.split(':')[0].split('.')[0].split('@')[0]
    if not value or value in ('C', 'POSIX'):
        return []
    if '_' in value:
        return [value, value.split('_')[0]]
    return [value]


def command_arguments(exec_value):
    """Argument list for an Exec line, with every field code removed."""
    try:
        tokens = shlex.split(exec_value)
    except ValueError:
        return []
    arguments = []
    for token in tokens:
        if FIELD_CODE.fullmatch(token):
            continue
        arguments.append(token.replace('%%', '%'))
    return arguments


def _shown_here(section, desktop=DESKTOP_NAME):
    only = [part for part in section.get('OnlyShowIn', '').split(';') if part]
    never = [part for part in section.get('NotShowIn', '').split(';') if part]
    if only and desktop not in only:
        return False
    return desktop not in never


def read_entry(path, locales=(), desktop=DESKTOP_NAME):
    """One launchable application, or None when the file is not one."""
    parser = _parser()
    try:
        parser.read_string(Path(path).read_text(encoding='utf-8', errors='replace'))
        section = parser['Desktop Entry']
    except (OSError, KeyError, configparser.Error, UnicodeError):
        return None
    if section.get('Type', 'Application') != 'Application':
        return None
    if section.get('NoDisplay', '').strip().lower() == 'true':
        return None
    if section.get('Hidden', '').strip().lower() == 'true':
        return None
    if not _shown_here(section, desktop):
        return None
    name = _localized(section, 'Name', locales).strip()
    exec_value = section.get('Exec', '').strip()
    if not name or not exec_value:
        return None
    arguments = command_arguments(exec_value)
    if not arguments:
        return None
    try_exec = section.get('TryExec', '').strip()
    if try_exec and not _executable(try_exec):
        return None
    keywords = [part for part in section.get('Keywords', '').split(';') if part]
    categories = [part for part in section.get('Categories', '').split(';') if part]
    return {
        'id': Path(path).name,
        'path': str(path),
        'name': name,
        'generic': _localized(section, 'GenericName', locales).strip(),
        'comment': _localized(section, 'Comment', locales).strip(),
        'icon': section.get('Icon', '').strip(),
        'arguments': arguments,
        'terminal': section.get('Terminal', '').strip().lower() == 'true',
        'keywords': keywords,
        'categories': categories,
    }


def _executable(name):
    if '/' in name:
        return os.access(name, os.X_OK)
    for directory in os.environ.get('PATH', '/usr/bin:/bin').split(':'):
        if directory and os.access(os.path.join(directory, name), os.X_OK):
            return True
    return False


def scan(directories=None, locales=None, desktop=DESKTOP_NAME):
    """Every launchable application, ordered by name, deduplicated by identifier."""
    directories = data_directories() if directories is None else [Path(item) for item in directories]
    locales = locale_candidates() if locales is None else list(locales)
    entries = {}
    for directory in directories:
        try:
            files = sorted(directory.rglob('*.desktop'))
        except OSError:
            continue
        for path in files:
            try:
                identifier = str(path.relative_to(directory)).replace('/', '-')
            except ValueError:
                identifier = path.name
            if identifier in entries:
                continue
            entry = read_entry(path, locales, desktop)
            if entry is not None:
                entries[identifier] = dict(entry, id=identifier)
    return sorted(entries.values(), key=lambda item: (item['name'].casefold(), item['id']))


def fuzzy_score(query, text):
    """Subsequence score for one field, or None when the query does not fit.

    Higher is better. A run of adjacent characters, a match at a word start and
    a match at the very beginning all earn more than a scattered subsequence,
    so "fox" prefers "Firefox" over "Fractal Object Explorer".
    """
    if not query:
        return 0.0
    haystack = text.casefold()
    needle = query.casefold()
    position, score, previous = 0, 0.0, -2
    for character in needle:
        found = haystack.find(character, position)
        if found < 0:
            return None
        if found == previous + 1:
            score += 6.0
        elif found == 0:
            score += 8.0
        elif haystack[found - 1] in ' -_./:':
            score += 5.0
        else:
            score += 1.0
        previous = found
        position = found + 1
    if haystack.startswith(needle):
        score += 12.0
    coverage = len(needle) / max(1, len(haystack))
    return score + coverage * 6.0


def entry_score(query, entry):
    """Best score across an entry's searchable fields, weighted by field."""
    fields = ((entry.get('name', ''), 1.0), (entry.get('generic', ''), 0.72),
              (' '.join(entry.get('keywords', ())), 0.6),
              (entry.get('comment', ''), 0.42),
              (' '.join(entry.get('categories', ())), 0.3),
              (entry.get('id', '').removesuffix('.desktop'), 0.66))
    best = None
    for text, weight in fields:
        if not text:
            continue
        score = fuzzy_score(query, text)
        if score is not None:
            score *= weight
            if best is None or score > best:
                best = score
    return best


def search(entries, query):
    """Entries matching the query, best first; the full list when it is empty."""
    query = (query or '').strip()
    if not query:
        return list(entries)
    scored = []
    for entry in entries:
        score = entry_score(query, entry)
        if score is not None:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1]['name'].casefold()))
    return [entry for _, entry in scored]
