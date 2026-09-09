"""Versioned user settings with bounded reads and atomic, private writes."""
from dataclasses import dataclass, field, fields
import json
import os
from pathlib import Path
import stat
import tempfile


MAX_CONFIG_BYTES = 65536
CONFIG_VERSION = 1

# The guide reads outward from the most local context: the focused application
# sits inside tmux, inside its terminal, inside the desktop, inside the system.
# ``diagnostics`` only appears when a profile file failed to load.
SECTION_IDS = ('application', 'tmux', 'terminal', 'desktop', 'system', 'diagnostics')


class ConfigError(ValueError):
    """A configuration file could not be read, validated, or saved safely."""


def _display_text(value, limit, what):
    """Accept only a single, already-tidy display line."""
    if (not isinstance(value, str) or not value.strip() or value.strip() != value
            or len(value) > limit or any(character < ' ' or character == '\x7f'
                                         for character in value)):
        raise ConfigError(f'{what} must be one tidy line of at most {limit} characters')
    return value


def _section_names(values, what):
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise ConfigError(f'sections.{what} must be a list of section names')
    if len(values) > 32:
        raise ConfigError(f'sections.{what} lists more than 32 sections')
    names = tuple(_display_text(value, 64, f'a sections.{what} name') for value in values)
    if len(set(names)) != len(names):
        raise ConfigError(f'sections.{what} repeats a section')
    return names


def _custom_section(name, raw):
    if not isinstance(raw, dict) or set(raw) - {'title', 'coverage', 'rows'}:
        raise ConfigError(f'sections.custom.{name} accepts only title, coverage and rows')
    coverage = _display_text(raw.get('coverage', 'Partial local section'), 80,
                             f'sections.custom.{name}.coverage')
    # A local section describes some of your keys; it cannot claim to be complete.
    if not coverage.startswith('Partial'):
        raise ConfigError(f'sections.custom.{name}.coverage must begin with "Partial"')
    rows = raw.get('rows', ())
    if isinstance(rows, str) or not isinstance(rows, (list, tuple)) or len(rows) > 100:
        raise ConfigError(f'sections.custom.{name}.rows must be a list of at most 100 rows')
    pairs = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'key', 'description'}:
            raise ConfigError(f'each sections.custom.{name} row needs key and description')
        pairs.append((_display_text(row['key'], 80, 'a row key'),
                      _display_text(row['description'], 180, 'a row description')))
    return (name, _display_text(raw.get('title', name), 80, f'sections.custom.{name}.title'),
            coverage, tuple(pairs))


@dataclass(frozen=True)
class SectionLayout:
    """Which guide sections appear, in what order, and under what titles.

    Every field is a tuple so the whole settings value stays immutable and
    comparable. ``order`` lists sections first to last and anything omitted
    keeps its default place after them, so a partial order stays valid.
    ``hidden`` drops sections, ``titles`` renames them, and ``custom`` defines
    sections of your own that are ordered, renamed and hidden like built-ins.
    """

    order: tuple = SECTION_IDS
    hidden: tuple = ()
    titles: tuple = ()
    custom: tuple = ()

    @classmethod
    def from_document(cls, raw):
        if not isinstance(raw, dict) or set(raw) - {'order', 'hidden', 'titles', 'custom'}:
            raise ConfigError('sections accepts only order, hidden, titles and custom')
        custom_raw = raw.get('custom', {})
        if not isinstance(custom_raw, dict) or len(custom_raw) > 16:
            raise ConfigError('sections.custom must be an object of at most 16 sections')
        custom = []
        for name, entry in custom_raw.items():
            name = _display_text(name, 64, 'a sections.custom name')
            if name in SECTION_IDS:
                raise ConfigError(f'sections.custom.{name} shadows a built-in section')
            custom.append(_custom_section(name, entry))
        titles_raw = raw.get('titles', {})
        if not isinstance(titles_raw, dict):
            raise ConfigError('sections.titles must be an object of section names')
        titles = tuple((_display_text(name, 64, 'a sections.titles name'),
                        _display_text(value, 80, 'a section title'))
                       for name, value in titles_raw.items())
        layout = cls(order=_section_names(raw.get('order', SECTION_IDS), 'order'),
                     hidden=_section_names(raw.get('hidden', ()), 'hidden'),
                     titles=titles, custom=tuple(custom))
        known = set(SECTION_IDS) | {entry[0] for entry in layout.custom}
        unknown = sorted((set(layout.order) | set(layout.hidden)
                          | {name for name, _ in layout.titles}) - known)
        if unknown:
            raise ConfigError('unknown section: ' + ', '.join(unknown))
        return layout

    def as_document(self):
        return {
            'order': list(self.order),
            'hidden': list(self.hidden),
            'titles': {name: title for name, title in self.titles},
            'custom': {name: {'title': title, 'coverage': coverage,
                              'rows': [{'key': key, 'description': description}
                                       for key, description in rows]}
                       for name, title, coverage, rows in self.custom},
        }

    def arrange(self, built):
        """Return the built sections as a display list, ordered and renamed.

        ``built`` maps section name to section. Custom sections fill in names
        the desktop did not build, unlisted sections follow in default order,
        and hiding is applied last so renaming a hidden section stays harmless.
        """
        sections = dict(built)
        for name, title, coverage, rows in self.custom:
            sections.setdefault(name, {
                'title': title, 'coverage': coverage,
                'rows': [{'key': key, 'description': description}
                         for key, description in rows]})
        titles = dict(self.titles)
        hidden = set(self.hidden)
        arranged = []
        for name in dict.fromkeys((*self.order, *SECTION_IDS, *sections)):
            section = sections.get(name)
            if section is None or name in hidden:
                continue
            title = titles.get(name)
            # Replacing an existing key keeps its position, so a section stays
            # shaped {title, coverage, rows} in that order.
            arranged.append({**section, 'title': title} if title else section)
        return arranged


@dataclass(frozen=True)
class AppConfig:
    hold_delay_ms: int = 500
    dismiss_mode: str = 'focus_loss'
    key_delay_ms: int = 12
    release_timeout_ms: int = 5000
    profiles_path: str = ''
    sections: SectionLayout = SectionLayout()
    # JSON text keeps the frozen value immutable while retaining future fields.
    _extra_json: str = field(default='{}', repr=False, compare=False)


def config_path():
    """Return the XDG settings path without creating any directories."""
    configured = os.environ.get('XDG_CONFIG_HOME', '')
    directory = Path(configured) if configured else Path.home() / '.config'
    if not directory.is_absolute():
        directory = Path.home() / '.config'
    return directory / 'superhold/config.json'


def _path(path):
    return config_path() if path is None else Path(path).expanduser()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f'Duplicate configuration field: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ConfigError(f'Invalid JSON number: {value}')


def _read_document(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ConfigError(f'Cannot read {path}: {error.strerror}') from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ConfigError(f'{path} must be a regular file owned by you')
        if metadata.st_size > MAX_CONFIG_BYTES:
            raise ConfigError(f'{path} exceeds the 64 KiB configuration limit')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            data = stream.read(MAX_CONFIG_BYTES + 1)
        if len(data) > MAX_CONFIG_BYTES:
            raise ConfigError(f'{path} exceeds the 64 KiB configuration limit')
        document = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object,
                              parse_constant=_invalid_constant)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ConfigError(f'Cannot parse {path}: {error}') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(document, dict):
        raise ConfigError(f'{path} must contain a JSON object')
    return document


def _validated(document):
    version = document.get('version', CONFIG_VERSION)
    if type(version) is not int or version != CONFIG_VERSION:
        raise ConfigError('Unsupported configuration version; expected version 1')
    defaults = AppConfig()
    values = {}
    for name, minimum, maximum in (
        ('hold_delay_ms', 100, 5000),
        ('key_delay_ms', 0, 250),
        ('release_timeout_ms', 250, 30000),
    ):
        value = document.get(name, getattr(defaults, name))
        if type(value) is not int or not minimum <= value <= maximum:
            raise ConfigError(f'{name} must be an integer from {minimum} to {maximum}')
        values[name] = value
    dismiss_mode = document.get('dismiss_mode', defaults.dismiss_mode)
    if not isinstance(dismiss_mode, str) or dismiss_mode not in ('release', 'focus_loss'):
        raise ConfigError('dismiss_mode must be "release" or "focus_loss"')
    values['dismiss_mode'] = dismiss_mode
    profiles_path = document.get('profiles_path', defaults.profiles_path)
    if not isinstance(profiles_path, str) or '\x00' in profiles_path or len(profiles_path) > 4096:
        raise ConfigError('profiles_path must be a path string of at most 4096 characters')
    if profiles_path and not (Path(profiles_path).is_absolute() or profiles_path.startswith('~/')):
        raise ConfigError('profiles_path must be empty, absolute, or start with ~/')
    values['profiles_path'] = profiles_path
    sections = document.get('sections', defaults.sections)
    values['sections'] = (sections if isinstance(sections, SectionLayout)
                          else SectionLayout.from_document(sections))
    names = set(values) | {'version'}
    values['_extra_json'] = json.dumps({key: value for key, value in document.items()
                                       if key not in names}, ensure_ascii=False)
    return AppConfig(**values)


def load_config(path=None):
    """Load settings; a missing file means defaults, an invalid file is an error."""
    return _validated(_read_document(_path(path)))


def save_config(config, path=None):
    """Atomically save settings, retaining unknown fields and invalid originals."""
    if not isinstance(config, AppConfig):
        raise ConfigError('Settings must be an AppConfig value')
    path = _path(path)
    values = {item.name: getattr(config, item.name) for item in fields(AppConfig)
              if not item.name.startswith('_')}
    values['sections'] = values['sections'].as_document()
    _validated(values)
    existing = _read_document(path)
    _validated(existing)  # Never replace an existing malformed or future-version file.
    try:
        extras = json.loads(config._extra_json)
        if not isinstance(extras, dict):
            raise ValueError('expected an object')
        document = {**existing, **extras, **values, 'version': CONFIG_VERSION}
        encoded = (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False)
                   + '\n').encode('utf-8')
    except (ValueError, TypeError, RecursionError) as error:
        raise ConfigError(f'Cannot encode settings: {error}') from error
    if len(encoded) > MAX_CONFIG_BYTES:
        raise ConfigError('Settings exceed the 64 KiB configuration limit')
    temporary = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.stat().st_uid != os.getuid():
            raise ConfigError(f'{path.parent} must be owned by you')
        descriptor, temporary = tempfile.mkstemp(prefix='.config-', suffix='.tmp',
                                                 dir=path.parent)
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ConfigError(f'Refusing to replace symbolic link {path}')
        os.replace(temporary, path)
        temporary = None
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ConfigError(f'Cannot save {path}: {error.strerror or error}') from error
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
