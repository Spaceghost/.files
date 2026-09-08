"""Scrollable local Scripture history, with append-only notes and study material."""
import subprocess
import json

import scripture_history as history


class Reader:
    def __init__(self, database):
        self.database = database
        self.identifier = None

    def latest(self):
        rows = history.entries(self.database, limit=1)
        self.identifier = rows[0]['id'] if rows else None
        return self.read()

    def read(self):
        return history.get(self.identifier, self.database) if self.identifier else None

    def move(self, direction):
        target = history.adjacent(self.identifier, direction, self.database) if self.identifier else None
        if target is not None:
            self.identifier = target
        return self.read()

    def add(self, text, kind='note', source_url=''):
        if self.identifier is None:
            raise ValueError('Select a history entry first')
        document = {'text': text, 'provenance': {'method': 'user-supplied'}}
        if source_url:
            document['source_url'] = source_url
        return history.append(self.identifier, document, kind=kind, database=self.database)


def run(helper, database):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gio, GLib
    from overlay_theme import gtk_css, read_palette

    model = Reader(database)
    app = Gtk.Application(application_id='com.mbp_intel.scripture.history',
                          flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(application):
        window = Gtk.ApplicationWindow(application=application)
        window.set_title('Scripture history')
        window.set_default_size(1000, 760)
        window.set_name('scripture-history')
        provider = Gtk.CssProvider()
        stylesheet = '''
            #scripture-history { background: @theme_background; color: @theme_foreground; }
            #scripture-history textview, #scripture-history textview text {
                background: @theme_background; color: @theme_foreground;
                font-family: serif; font-size: 17px;
            }
            #scripture-history button { padding: 7px 12px; }
        '''
        palette = None

        def refresh_theme():
            nonlocal palette
            selected = read_palette()
            if selected != palette:
                provider.load_from_data(gtk_css(stylesheet, selected))
                palette = selected
            return GLib.SOURCE_CONTINUE

        refresh_theme()
        # GTK caches the user's stylesheet at startup. The live reader palette
        # must win over that older file without rebuilding widgets or drafts.
        Gtk.StyleContext.add_provider_for_screen(window.get_screen(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        theme_timer = GLib.timeout_add_seconds(1, refresh_theme)

        def stop_theme(*_args):
            GLib.source_remove(theme_timer)
            Gtk.StyleContext.remove_provider_for_screen(window.get_screen(), provider)

        window.connect('destroy', stop_theme)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        window.add(root)
        toolbar = Gtk.Box(spacing=8)
        root.pack_start(toolbar, False, False, 0)
        older, newer, latest = [Gtk.Button(label=title) for title in ('← Older', 'Newer →', 'Latest')]
        use = Gtk.Button(label='Show this passage on desktop')
        for button in (older, newer, latest, use):
            toolbar.pack_start(button, False, False, 0)
        position = Gtk.Label(xalign=1)
        toolbar.pack_end(position, True, True, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            left_margin=14, right_margin=14, top_margin=12, bottom_margin=12)
        view.set_accepts_tab(False)
        scroll.add(view)
        root.pack_start(scroll, True, True, 0)
        metadata = Gtk.Expander(label='Full entry data')
        metadata_scroll = Gtk.ScrolledWindow()
        metadata_scroll.set_min_content_height(150)
        metadata_view = Gtk.TextView(editable=False, cursor_visible=False,
                                     wrap_mode=Gtk.WrapMode.WORD_CHAR)
        metadata_scroll.add(metadata_view)
        metadata.add(metadata_scroll)
        root.pack_start(metadata, False, False, 0)
        details = Gtk.Expander(label='Add a note, research, or generated material to this entry')
        root.pack_start(details, False, False, 0)
        editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        details.add(editor)
        controls = Gtk.Box(spacing=6)
        kind = Gtk.ComboBoxText()
        for identifier, title in (('note', 'Note'), ('research', 'Research'), ('generated', 'Generated material')):
            kind.append(identifier, title)
        kind.set_active_id('note')
        controls.pack_start(kind, False, False, 0)
        source = Gtk.Entry(placeholder_text='Source URL, if applicable')
        controls.pack_start(source, True, True, 0)
        save = Gtk.Button(label='Save additional material')
        controls.pack_start(save, False, False, 0)
        editor.pack_start(controls, False, False, 0)
        note_scroll = Gtk.ScrolledWindow()
        note_scroll.set_min_content_height(110)
        note = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        note_scroll.add(note)
        editor.pack_start(note_scroll, True, True, 0)
        status = Gtk.Label(xalign=0)
        status.set_line_wrap(True)
        root.pack_start(status, False, False, 0)
        drafts = {}

        def display(entry, reset=True):
            view.get_buffer().set_text(history.render(entry) if entry else
                                       'No saved passages yet. Choose a Scripture passage to begin your history.')
            position.set_text('Entry ' + str(entry['id']) if entry else '')
            metadata_view.get_buffer().set_text(json.dumps(entry, ensure_ascii=False, indent=2) if entry else '')
            older.set_sensitive(bool(entry and history.adjacent(entry['id'], 'older', database)))
            newer.set_sensitive(bool(entry and history.adjacent(entry['id'], 'newer', database)))
            use.set_sensitive(bool(entry))
            save.set_sensitive(bool(entry))
            if reset:
                scroll.get_vadjustment().set_value(0)

        def navigate(direction=None):
            try:
                buffer = note.get_buffer()
                if model.identifier is not None:
                    drafts[model.identifier] = (buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True),
                                                 kind.get_active_id(), source.get_text())
                display(model.move(direction) if direction else model.latest())
                draft, draft_kind, draft_source = drafts.get(model.identifier, ('', 'note', ''))
                buffer.set_text(draft)
                kind.set_active_id(draft_kind)
                source.set_text(draft_source)
                status.set_text('')
            except (ValueError, OSError, history.sqlite3.Error) as error:
                status.set_text(str(error))

        def add(_button):
            buffer = note.get_buffer()
            text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            if not text.strip():
                status.set_text('Write some additional material before saving.')
                return
            try:
                model.add(text, kind.get_active_id(), source.get_text().strip())
                buffer.set_text('')
                source.set_text('')
                display(model.read(), reset=False)
                status.set_text('Saved to this history entry.')
            except (ValueError, OSError, history.sqlite3.Error) as error:
                status.set_text(str(error))

        def select(_button):
            if model.identifier:
                try:
                    process = subprocess.Popen([str(helper), 'history-use', str(model.identifier)],
                                               start_new_session=True)
                except OSError as error:
                    status.set_text(str(error))
                    return
                use.set_sensitive(False)
                status.set_text('Selecting this passage…')

                def completed():
                    result = process.poll()
                    if result is None:
                        return GLib.SOURCE_CONTINUE
                    use.set_sensitive(bool(model.identifier))
                    status.set_text('Selected for the desktop; automatic rotation resumes in one hour.'
                                    if result == 0 else 'The passage could not be selected. Please try again.')
                    return GLib.SOURCE_REMOVE

                GLib.timeout_add(100, completed)

        older.connect('clicked', lambda *_: navigate('older'))
        newer.connect('clicked', lambda *_: navigate('newer'))
        latest.connect('clicked', lambda *_: navigate())
        use.connect('clicked', select)
        save.connect('clicked', add)
        navigate()
        window.show_all()

    app.connect('activate', activate)
    return app.run([])
