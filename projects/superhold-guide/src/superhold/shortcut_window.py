"""Searchable, clickable native GTK shortcut guide."""
from .shortcut_overlay import GtkShortcutOverlay
from .shortcut_search import search_shortcuts


class InteractiveOverlay(GtkShortcutOverlay):
    CSS = GtkShortcutOverlay.CSS + b"""
    #superhold-panel button {
        background-image: none;
        background-color: mix(@theme_bg_color, @theme_fg_color, 0.08);
        border: 1px solid @borders;
        color: @theme_fg_color;
        box-shadow: none;
        text-shadow: none;
    }
    #superhold-panel button:hover {
        background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.25);
    }
    #superhold-panel button:disabled {
        color: @insensitive_fg_color; background-color: @theme_bg_color;
    }
    #superhold-panel entry {
        background-image: none;
        background-color: @theme_base_color;
        color: @theme_text_color;
        border: 1px solid @theme_selected_bg_color;
        caret-color: @theme_text_color;
    }
    #superhold-results { background-color: @theme_base_color; color: @theme_text_color; }
    #superhold-results row { border-bottom: 1px solid @borders; }
    #superhold-results row:hover {
        background-color: mix(@theme_base_color, @theme_selected_bg_color, 0.15);
    }
    #superhold-results row:selected { background-color: @theme_selected_bg_color; }
    #superhold-results row:selected label { color: @theme_selected_fg_color; }
    #superhold-results row:selected #superhold-key {
        background-color: @theme_selected_bg_color;
        border-color: alpha(@theme_selected_fg_color, 0.35);
        color: @theme_selected_fg_color;
    }
    """
    def __init__(self, *, persistent=True, on_settings=None):
        super().__init__(focusable=persistent)
        self.on_activate = lambda action: None
        self.on_dismiss = self.hide
        self.on_settings = on_settings
        self._mapped = False
        self._had_focus = False
        self._map_generation = 0
        self._snapshot = {}
        self._error = None
        self.search = None
        self.results = None
        self.window.connect('focus-in-event', self._focus_in)
        self.window.connect('focus-out-event', self._focus_out)
        self.window.connect('delete-event', self._delete)
        self.window.connect('key-press-event', self._key_press)

    def _focus_in(self, *_args):
        if self._mapped:
            self._had_focus = True
        return False

    def _focus_out(self, *_args):
        if self.focusable and self._mapped and self._had_focus:
            self.on_dismiss()
        return False

    def _delete(self, *_args):
        self.on_dismiss()
        return True

    def _activate_selected(self, *_args):
        row = self.results.get_selected_row() if self.results else None
        if row is not None and row.shortcut['action'] is not None:
            self.on_activate(row.shortcut['action'])

    def _key_press(self, _window, event):
        if event.keyval == self.Gdk.KEY_Escape:
            self.on_dismiss()
            return True
        if event.keyval in (self.Gdk.KEY_Return, self.Gdk.KEY_KP_Enter):
            # SearchEntry has its own activate signal; intercept only when the
            # entry is focused so Enter on Settings/Close keeps native behavior.
            if self.search and self.search.has_focus():
                self._activate_selected()
                return True
        if event.keyval in (self.Gdk.KEY_Down, self.Gdk.KEY_Up) and self.results:
            rows = [row for row in self.results.get_children() if row.get_selectable()]
            if rows:
                selected = self.results.get_selected_row()
                index = rows.index(selected) if selected in rows else 0
                index = min(len(rows) - 1, index + 1) if event.keyval == self.Gdk.KEY_Down else max(0, index - 1)
                self.results.select_row(rows[index])
                allocation = rows[index].get_allocation()
                adjustment = self.scroll.get_vadjustment()
                adjustment.clamp_page(allocation.y, allocation.y + allocation.height)
            return True
        return False

    def _header(self, title):
        heading = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=12)
        text = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=3)
        text.pack_start(self._label(title, 'superhold-title'), False, False, 0)
        hint = ('Search shortcuts • Enter runs the selected result • Click away to close'
                if self.focusable else 'Click a shortcut • Release Super to close')
        text.pack_start(self._label(hint, 'superhold-hint'), False, False, 0)
        heading.pack_start(text, True, True, 0)
        if self.on_settings:
            settings = self.Gtk.Button.new_with_label('Settings')
            settings.connect('clicked', lambda *_args: self.on_settings())
            heading.pack_start(settings, False, False, 0)
        close = self.Gtk.Button.new_with_label('Close')
        close.connect('clicked', lambda *_args: self.on_dismiss())
        heading.pack_start(close, False, False, 0)
        self.panel.pack_start(heading, False, False, 0)

    def _render_results(self, *_args):
        for child in self.results.get_children():
            self.results.remove(child)
        query = self.search.get_text() if self.search else ''
        matches = search_shortcuts(self._snapshot, query)
        first = None
        previous_section = None
        for match in matches:
            row = self.Gtk.ListBoxRow()
            row.shortcut = match
            action = match['action']
            row.set_selectable(action is not None)
            row.set_activatable(action is not None)
            card = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=5)
            card.set_border_width(7)
            if match['section_index'] != previous_section:
                title = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=8)
                title.pack_start(self._label(match['section'], 'superhold-section-title'), True, True, 0)
                title.pack_end(self._label(match['coverage'], 'superhold-coverage'), False, False, 0)
                card.pack_start(title, False, False, 0)
                previous_section = match['section_index']
            line = self.Gtk.Box(orientation=self.Gtk.Orientation.HORIZONTAL, spacing=12)
            button = self.Gtk.Button.new_with_label(match['key'])
            button.set_name('superhold-key')
            button.set_size_request(190, -1)
            button.set_sensitive(action is not None)
            button.set_can_focus(False)
            if action is not None:
                button.connect('clicked', lambda _button, chosen=action: self.on_activate(chosen))
                first = first or row
            else:
                button.set_tooltip_text(match['unavailable_reason'])
            line.pack_start(button, False, False, 0)
            details = self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL, spacing=3)
            details.pack_start(self._label(match['description'], 'superhold-description'), False, False, 0)
            if action is None and match['unavailable_reason']:
                details.pack_start(self._label(match['unavailable_reason'], 'superhold-coverage'), False, False, 0)
            line.pack_start(details, True, True, 0)
            card.pack_start(line, False, False, 0)
            row.add(card)
            self.results.add(row)
        if first is not None:
            self.results.select_row(first)
        self.count.set_text(f'{len(matches)} shortcuts' if matches else 'No matching shortcuts')
        self.results.show_all()
        self.scroll.get_vadjustment().set_value(0)

    def _check_initial_focus(self, generation):
        if (self._mapped and self._map_generation == generation
                and self.focusable and not self._had_focus):
            import sys
            print('superhold: Sway did not focus the guide; leave fullscreen and try again.',
                  file=sys.stderr)
            self.on_dismiss()
        return False

    def show(self, snapshot):
        self._clear()
        self._snapshot = snapshot
        monitor = self._select_monitor(snapshot.get('output'), snapshot.get('_output_rect'))
        self._bound_window(monitor)
        self._header(f"{snapshot.get('app') or 'Current context'} shortcuts")
        self.search = None
        if self.focusable:
            self.search = self.Gtk.SearchEntry()
            self.search.set_placeholder_text('Search keys, actions, or context…')
            self.search.connect('changed', self._render_results)
            self.search.connect('activate', self._activate_selected)
            self.search.connect('stop-search', lambda *_args: self.on_dismiss())
            self.panel.pack_start(self.search, False, False, 0)
        self.count = self._label('', 'superhold-coverage')
        self.panel.pack_start(self.count, False, False, 0)
        self.scroll = self.Gtk.ScrolledWindow()
        self.scroll.set_policy(self.Gtk.PolicyType.NEVER, self.Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_overlay_scrolling(False)
        self.results = self.Gtk.ListBox()
        self.results.set_name('superhold-results')
        self.results.set_selection_mode(self.Gtk.SelectionMode.SINGLE)
        self.results.set_activate_on_single_click(True)
        self.results.connect('row-activated', lambda _list, row: self.on_activate(row.shortcut['action'])
                             if row.shortcut['action'] is not None else None)
        self.scroll.add(self.results)
        self.panel.pack_start(self.scroll, True, True, 0)
        self._render_results()
        self._had_focus = False
        self._map_generation += 1
        self._mapped = True
        self.window.show_all()
        if self.focusable:
            from gi.repository import GLib
            GLib.timeout_add(1000, self._check_initial_focus, self._map_generation)
        if self.search:
            self.search.grab_focus()

    @property
    def has_error(self):
        return self._error is not None

    def _error_destroyed(self, *_args):
        self._error = None

    def show_error(self, message):
        if self._error:
            self._error.destroy()
        self._error = self.Gtk.MessageDialog(
            message_type=self.Gtk.MessageType.INFO,
            buttons=self.Gtk.ButtonsType.CLOSE, text='Shortcut was not sent')
        self._error.set_title('Superhold')
        self._error.format_secondary_text(message)
        self._error.connect('response', lambda dialog, _response: dialog.destroy())
        self._error.connect('destroy', self._error_destroyed)
        self._error.show_all()

    def hide(self):
        self._map_generation += 1
        self._mapped = False
        self._had_focus = False
        super().hide()

    def close(self):
        if self._error:
            self._error.destroy()
            self._error = None
        super().close()
