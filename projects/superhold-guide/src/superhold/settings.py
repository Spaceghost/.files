"""The normal desktop settings window; GTK is imported only when opened."""
from dataclasses import replace
from pathlib import Path

from .config import AppConfig, ConfigError, config_path, load_config, save_config


def show_settings(path=None, on_saved=None):
    """Open settings and run its GTK application, returning its exit status.

    ``on_saved`` receives the saved AppConfig. The window itself does not start,
    stop, or reconfigure a desktop session, and Reset only edits the form.
    """
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        from gi.repository import Gio, Gtk
    except (ImportError, ValueError) as error:
        raise RuntimeError('Settings require GTK 3 and Python GObject bindings') from error

    destination = config_path() if path is None else Path(path).expanduser()
    application = Gtk.Application(application_id='org.superhold.Settings',
                                  flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(app):
        try:
            original = load_config(destination)
            load_error = None
        except ConfigError as error:
            original = AppConfig()
            load_error = str(error)

        window = Gtk.ApplicationWindow(application=app)
        from .theme import DesktopTheme
        window.desktop_theme = DesktopTheme(window)
        window.set_title('Superhold Settings')
        window.set_default_size(620, -1)
        window.set_border_width(20)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        window.add(content)
        title = Gtk.Label(label='Superhold')
        title.set_xalign(0)
        title.get_style_context().add_class('title')
        content.pack_start(title, False, False, 0)
        introduction = Gtk.Label(label='Choose when shortcuts appear and how the window closes.')
        introduction.set_xalign(0)
        introduction.set_line_wrap(True)
        content.pack_start(introduction, False, False, 0)

        grid = Gtk.Grid(column_spacing=18, row_spacing=14)
        content.pack_start(grid, False, False, 0)

        def label_for(text, widget, row, target=grid):
            label = Gtk.Label(label=text)
            label.set_xalign(0)
            label.set_mnemonic_widget(widget)
            target.attach(label, 0, row, 1, 1)
            target.attach(widget, 1, row, 1, 1)
            widget.set_hexpand(True)

        def milliseconds(minimum, maximum, step):
            field = Gtk.SpinButton.new_with_range(minimum, maximum, step)
            field.set_numeric(True)
            field.set_alignment(1)
            return field

        hold_delay = milliseconds(100, 5000, 50)
        hold_delay.set_tooltip_text('How long to hold Super alone before opening the shortcut window.')
        label_for('Hold delay (ms)', hold_delay, 0)

        dismiss_mode = Gtk.ComboBoxText()
        dismiss_mode.append('focus_loss', 'Keep open until focus moves away')
        dismiss_mode.append('release', 'Close when Super is released')
        dismiss_mode.set_tooltip_text('Keeping the window open gives you time to choose a shortcut with the mouse.')
        label_for('Window behavior', dismiss_mode, 1)

        profiles = Gtk.Entry()
        profiles.set_placeholder_text('Use default shortcut profiles')
        profiles.set_tooltip_text('Optional absolute path or ~/ path to your shortcut profiles JSON file.')
        browse = Gtk.Button(label='Browse…')
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        path_box.pack_start(profiles, True, True, 0)
        path_box.pack_start(browse, False, False, 0)
        label_for('Shortcut profiles', path_box, 2)

        def choose_profiles(_button):
            chooser = Gtk.FileChooserDialog(title='Choose shortcut profiles', parent=window,
                                             action=Gtk.FileChooserAction.OPEN)
            chooser.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Choose', Gtk.ResponseType.ACCEPT)
            json_filter = Gtk.FileFilter()
            json_filter.set_name('JSON files')
            json_filter.add_pattern('*.json')
            chooser.add_filter(json_filter)
            if chooser.run() == Gtk.ResponseType.ACCEPT:
                profiles.set_text(chooser.get_filename())
            chooser.destroy()

        browse.connect('clicked', choose_profiles)

        advanced = Gtk.Expander(label='Shortcut delivery')
        advanced_grid = Gtk.Grid(column_spacing=18, row_spacing=14)
        advanced_grid.set_margin_top(12)
        advanced.add(advanced_grid)
        key_delay = milliseconds(0, 250, 1)
        key_delay.set_tooltip_text('Delay between injected key events. Increase this if an application misses keys.')
        label_for('Delay between keys (ms)', key_delay, 0, advanced_grid)
        release_timeout = milliseconds(250, 30000, 250)
        release_timeout.set_tooltip_text('A selected shortcut waits for held modifiers to be released, then cancels after this time.')
        label_for('Wait for held keys (ms)', release_timeout, 1, advanced_grid)
        content.pack_start(advanced, False, False, 0)

        notice = Gtk.Label(label='Changes are saved only when you select Save.')
        notice.set_xalign(0)
        notice.set_line_wrap(True)
        content.pack_start(notice, False, False, 0)
        location = Gtk.Label(label=f'Configuration file: {destination}')
        location.set_xalign(0)
        location.set_line_wrap(True)
        location.set_selectable(True)
        location.get_style_context().add_class('dim-label')
        content.pack_start(location, False, False, 0)

        error_label = Gtk.Label()
        error_label.set_xalign(0)
        error_label.set_line_wrap(True)
        error_label.get_style_context().add_class('error')
        content.pack_start(error_label, False, False, 0)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        defaults = Gtk.Button(label='Reset to Defaults')
        cancel = Gtk.Button(label='Cancel')
        save = Gtk.Button(label='Save')
        save.get_style_context().add_class('suggested-action')
        buttons.pack_start(defaults, False, False, 0)
        buttons.pack_end(save, False, False, 0)
        buttons.pack_end(cancel, False, False, 0)
        content.pack_end(buttons, False, False, 0)

        def set_values(config):
            hold_delay.set_value(config.hold_delay_ms)
            dismiss_mode.set_active_id(config.dismiss_mode)
            profiles.set_text(config.profiles_path)
            key_delay.set_value(config.key_delay_ms)
            release_timeout.set_value(config.release_timeout_ms)

        def save_values(_button):
            updated = replace(original, hold_delay_ms=hold_delay.get_value_as_int(),
                              dismiss_mode=dismiss_mode.get_active_id(),
                              key_delay_ms=key_delay.get_value_as_int(),
                              release_timeout_ms=release_timeout.get_value_as_int(),
                              profiles_path=profiles.get_text())
            try:
                save_config(updated, destination)
            except ConfigError as error:
                error_label.set_text(str(error))
                return
            if on_saved is not None:
                on_saved(updated)
            window.destroy()

        defaults.connect('clicked', lambda _button: set_values(AppConfig()))
        cancel.connect('clicked', lambda _button: window.destroy())
        save.connect('clicked', save_values)
        set_values(original)
        if load_error is not None:
            error_label.set_text(f'{load_error}\nFix the configuration file before saving; it has been preserved.')
            save.set_sensitive(False)
        window.show_all()

    application.connect('activate', activate)
    return application.run([])
