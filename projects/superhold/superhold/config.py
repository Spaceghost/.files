"""Small, validated XDG configuration without importing a GUI toolkit."""
from dataclasses import dataclass, field, replace
import math
import os
from pathlib import Path
import re
import stat
import tomllib
from types import MappingProxyType


# The guide reads outward from the most local context: the focused application
# sits inside tmux, inside its terminal, inside the desktop, inside the system.
# ``session`` only exists on the X11 backend, and ``diagnostics`` only appears
# when a local profile file failed to load, so both are skipped when absent.
SECTION_IDS = ('application', 'tmux', 'terminal', 'desktop', 'session',
               'system', 'diagnostics')

_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def config_home():
    configured = os.environ.get('XDG_CONFIG_HOME', '')
    return Path(configured) if configured and Path(configured).is_absolute() else Path.home() / '.config'


def _default_path(filename):
    primary = config_home() / 'superhold' / filename
    legacy = config_home() / 'hold-to-help' / filename
    # Existing invalid primary paths must never silently select legacy settings.
    return primary if os.path.lexists(primary) or not os.path.lexists(legacy) else legacy


def default_profiles_path():
    return _default_path('profiles.json')


def _text(value, limit, what):
    """Accept only a single, already-tidy display line."""
    if (not isinstance(value, str) or _CONTROL.search(value) or not value.strip()
            or value.strip() != value or len(value) > limit):
        raise ValueError(f'invalid {what}: {value!r}')
    return value


def _names(values, what):
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise ValueError(f'{what} must be a list of section names')
    if len(values) > 32:
        raise ValueError(f'{what} lists too many sections')
    names = tuple(_text(value, 64, 'section name') for value in values)
    if len(set(names)) != len(names):
        raise ValueError(f'{what} repeats a section')
    return names


def _custom_section(name, raw):
    if not isinstance(raw, dict) or set(raw) - {'title', 'coverage', 'rows'}:
        raise ValueError(f'invalid custom section: {name}')
    coverage = _text(raw.get('coverage', 'Partial local section'), 80, 'coverage')
    # A local section describes some of your keys; it cannot claim to be complete.
    if not coverage.startswith('Partial'):
        raise ValueError(f'custom section coverage must begin with "Partial": {name}')
    rows = raw.get('rows', ())
    if isinstance(rows, str) or not isinstance(rows, (list, tuple)) or len(rows) > 100:
        raise ValueError(f'invalid rows in custom section: {name}')
    clean = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'key', 'description'}:
            raise ValueError(f'invalid row in custom section: {name}')
        clean.append({'key': _text(row['key'], 80, 'row key'),
                      'description': _text(row['description'], 180, 'row description')})
    return {'title': _text(raw.get('title', name), 80, 'title'),
            'coverage': coverage, 'rows': clean}


@dataclass(frozen=True)
class Sections:
    """Which guide sections appear, in what order, and under what titles.

    ``order`` lists section names outermost-last; anything built but unlisted
    keeps its default place, so a partial order stays valid. ``hidden`` drops
    sections outright, ``titles`` renames them, and ``custom`` defines your own
    sections, which can then be ordered and renamed exactly like the built-ins.
    """

    order: tuple = SECTION_IDS
    hidden: tuple = ()
    titles: dict = field(default_factory=dict)
    custom: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.custom, dict) or len(self.custom) > 16:
            raise ValueError('custom must be a table of at most 16 sections')
        custom = {}
        for name, raw in self.custom.items():
            name = _text(name, 64, 'section name')
            if name in SECTION_IDS:
                raise ValueError(f'custom section shadows a built-in section: {name}')
            custom[name] = _custom_section(name, raw)
        if not isinstance(self.titles, dict):
            raise ValueError('titles must be a table of section names')
        titles = {_text(name, 64, 'section name'): _text(value, 80, 'title')
                  for name, value in self.titles.items()}
        order = _names(self.order, 'order')
        hidden = _names(self.hidden, 'hidden')
        unknown = sorted((set(order) | set(hidden) | set(titles))
                         - set(SECTION_IDS) - set(custom))
        if unknown:
            raise ValueError('unknown section: ' + ', '.join(unknown))
        object.__setattr__(self, 'order', order)
        object.__setattr__(self, 'hidden', frozenset(hidden))
        object.__setattr__(self, 'titles', MappingProxyType(titles))
        object.__setattr__(self, 'custom', MappingProxyType(custom))

    def arrange(self, built):
        """Return the built sections as a display list, ordered and renamed.

        ``built`` maps section name to section. Custom sections are added when
        the desktop did not build one of that name, unlisted sections follow in
        default order, and hidden sections are dropped last so that renaming or
        ordering a hidden section stays harmless.
        """
        sections = {**{name: dict(section) for name, section in self.custom.items()},
                    **built}
        sequence = dict.fromkeys((*self.order, *SECTION_IDS, *sections))
        arranged = []
        for name in sequence:
            section = sections.get(name)
            if section is None or name in self.hidden:
                continue
            title = self.titles.get(name)
            # Replacing an existing key keeps its position, so the public
            # section shape stays {title, coverage, rows} in that order.
            arranged.append({**section, 'title': title} if title else section)
        return arranged


@dataclass(frozen=True)
class Config:
    trigger: str = 'super'
    hold_seconds: float = 0.5
    backend: str = 'auto'
    sections: Sections = field(default_factory=Sections)

    def __post_init__(self):
        if not isinstance(self.sections, Sections):
            raise ValueError('sections must be a Sections configuration')
        if self.trigger not in ('super', 'capslock'):
            raise ValueError("trigger must be 'super' or 'capslock'")
        if self.backend not in ('auto', 'sway', 'x11'):
            raise ValueError("backend must be 'auto', 'sway' or 'x11'")
        duration = self.hold_seconds
        if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                or not math.isfinite(duration) or not 0.15 <= duration <= 3):
            raise ValueError('hold_seconds must be a finite number between 0.15 and 3')

    @property
    def trigger_label(self):
        return 'Caps Lock' if self.trigger == 'capslock' else 'Super'


def load_config(path=None, *, trigger=None, backend=None, hold_seconds=None):
    explicit = path is not None
    path = Path(path).expanduser() if explicit else _default_path('config.toml')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                raise ValueError('configuration must be a regular file of at most 64 KiB')
            document = tomllib.loads(stream.read(65537).decode('utf-8'))
    except FileNotFoundError:
        if explicit or os.path.lexists(path):
            raise ValueError(f'configuration file not found: {path}') from None
        document = {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f'cannot read configuration: {path}: {error}') from error
    if set(document) - {'trigger', 'hold_seconds', 'backend', 'sections'}:
        raise ValueError('unknown configuration key')
    raw_sections = document.pop('sections', {})
    if not isinstance(raw_sections, dict) or set(raw_sections) - {
            'order', 'hidden', 'titles', 'custom'}:
        raise ValueError('unknown [sections] key')
    config = Config(**document, sections=Sections(**raw_sections))
    overrides = {key: value for key, value in {
        'trigger': trigger, 'backend': backend, 'hold_seconds': hold_seconds,
    }.items() if value is not None}
    return replace(config, **overrides)
