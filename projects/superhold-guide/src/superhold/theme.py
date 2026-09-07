"""Follow desktop GTK preferences without changing any desktop files."""
import hashlib
import os
from pathlib import Path
import stat


MAX_THEME_BYTES = 1024 * 1024


def _gtk_bindings():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import GLib, Gtk
    return GLib, Gtk


def _config_directory():
    configured = Path(os.environ.get('XDG_CONFIG_HOME', '')).expanduser()
    return configured if configured.is_absolute() else Path.home() / '.config'


def _read_theme_file(path):
    """Read a bounded regular file, including through a desktop's symlink."""
    descriptor = None
    try:
        # A mistyped preference pointing at a FIFO must not block the UI loop.
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_THEME_BYTES:
            return None
        with os.fdopen(descriptor, 'rb') as source:
            descriptor = None
            content = source.read(MAX_THEME_BYTES + 1)
        if len(content) > MAX_THEME_BYTES:
            return None
        fingerprint = (str(path.resolve()), metadata.st_dev, metadata.st_ino,
                       metadata.st_mtime_ns, hashlib.sha256(content).digest())
        return fingerprint, content
    except (OSError, ValueError, RuntimeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


class DesktopTheme:
    """Reload user CSS while leaving GTK's session settings in control.

    GTK follows desktop settings itself, but its initial user CSS provider does
    not follow edits reliably. Keep a replaceable provider for that same XDG
    file. Polling also handles symlink target edits and atomic replacements.
    A broken or temporarily absent file leaves the last usable provider intact.
    """

    def __init__(self, window):
        self.GLib, self.Gtk = _gtk_bindings()
        self.window = window
        self.screen = window.get_screen()
        self.css_path = _config_directory() / 'gtk-3.0/gtk.css'
        self._provider = None
        self._fingerprint = None
        self._timer = None
        self._closed = False
        self._destroy_handler = window.connect('destroy', self.close)
        self.refresh()
        self._timer = self.GLib.timeout_add_seconds(1, self.refresh)

    def refresh(self):
        """Apply a complete valid replacement; keep the previous one on error."""
        if self._closed:
            return False
        snapshot = _read_theme_file(self.css_path)
        if snapshot is None or snapshot[0] == self._fingerprint:
            return True
        fingerprint, _content = snapshot
        candidate = self.Gtk.CssProvider()
        errors = []

        def parsing_error(_provider, _section, error):
            if error.code != self.Gtk.CssProviderError.DEPRECATED:
                errors.append(error)

        handler = candidate.connect('parsing-error', parsing_error)
        try:
            # Loading the real path preserves CSS @imports and relative URLs.
            candidate.load_from_path(str(self.css_path))
        except (self.GLib.Error, OSError, ValueError):
            errors.append(True)
        finally:
            candidate.disconnect(handler)
        # A writer may have replaced the file while GTK was reading it.
        current = _read_theme_file(self.css_path)
        if current is None or current[0] != fingerprint:
            return True
        self._fingerprint = fingerprint
        if errors:
            return True
        self.Gtk.StyleContext.add_provider_for_screen(
            self.screen, candidate, self.Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if self._provider is not None:
            self.Gtk.StyleContext.remove_provider_for_screen(self.screen, self._provider)
        self._provider = candidate
        return True

    def close(self, *_args):
        """Release the screen provider and periodic source with the window."""
        if self._closed:
            return
        self._closed = True
        if self._timer is not None:
            self.GLib.source_remove(self._timer)
            self._timer = None
        if self._provider is not None:
            self.Gtk.StyleContext.remove_provider_for_screen(self.screen, self._provider)
            self._provider = None
        self.window.disconnect(self._destroy_handler)
