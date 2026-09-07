"""Small, validated XDG configuration without importing a GUI toolkit."""
from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
import stat
import tomllib


def config_home():
    configured = os.environ.get('XDG_CONFIG_HOME', '')
    return Path(configured) if configured and Path(configured).is_absolute() else Path.home() / '.config'


def default_profiles_path():
    return config_home() / 'hold-to-help/profiles.json'


@dataclass(frozen=True)
class Config:
    trigger: str = 'super'
    hold_seconds: float = 0.5
    backend: str = 'auto'

    def __post_init__(self):
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
    path = Path(path).expanduser() if explicit else config_home() / 'hold-to-help/config.toml'
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                raise ValueError('configuration must be a regular file of at most 64 KiB')
            document = tomllib.loads(stream.read(65537).decode('utf-8'))
    except FileNotFoundError:
        if explicit:
            raise ValueError(f'configuration file not found: {path}') from None
        document = {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f'cannot read configuration: {path}: {error}') from error
    if set(document) - {'trigger', 'hold_seconds', 'backend'}:
        raise ValueError('unknown configuration key')
    config = Config(**document)
    overrides = {key: value for key, value in {
        'trigger': trigger, 'backend': backend, 'hold_seconds': hold_seconds,
    }.items() if value is not None}
    return replace(config, **overrides)
