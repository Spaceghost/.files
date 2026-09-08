"""A live history reader follows theme changes without losing private draft state."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


def native_reader(output):
    import hashlib
    import traceback
    sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
    import scripture_history as history
    import overlay_theme
    from scripture_history_reader import run
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gtk, Gdk, GLib

    themes = Path.home() / 'themes'
    themes.mkdir()
    for identity, background, foreground in (('warm', '#202a30', '#ddeeff'),
                                               ('cool', '#381533', '#ffccaa')):
        (themes / (identity + '.json')).write_text(json.dumps({
            'palette': {'background': background, 'foreground': foreground}}))
    (themes / 'current').write_text('warm')
    overlay_theme.read_palette.__defaults__ = (themes,)
    database = history.database_path()
    for number in (1, 2):
        history.select({'kind': 'study-note', 'reference': f'John 1:{number}',
                        'text': f'Synthetic full passage {number}',
                        'reflection': '\n'.join(f'Synthetic study line {line}' for line in range(80)),
                        'provenance': {'method': 'fixture; no model or network'}}, database, now=number)
    original_database = database.read_bytes()
    result = {'checks': [], 'failures': [], 'source_sha256': hashlib.sha256(
        (REPO / 'alpine/desktop/.local/lib/oldbook/scripture_history_reader.py').read_bytes()).hexdigest()}

    def walk(widget):
        yield widget
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                yield from walk(child)

    def content(widget):
        buffer = widget.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

    def photograph(window, name):
        allocation = window.get_allocation()
        picture = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, allocation.width, allocation.height)
        picture.savev(str(output / name), 'png', [], [])

    def color(widget):
        value = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        return '#%02x%02x%02x' % tuple(round(getattr(value, key) * 255) for key in ('red', 'green', 'blue'))

    def begin():
        windows = [window for window in Gtk.Window.list_toplevels() if window.get_title() == 'Scripture history']
        if not windows:
            return GLib.SOURCE_CONTINUE
        window = windows[0]
        try:
            widgets = list(walk(window))
            buttons = {widget.get_label(): widget for widget in widgets if isinstance(widget, Gtk.Button)}
            views = [widget for widget in widgets if isinstance(widget, Gtk.TextView)]
            reader = next(widget for widget in views if not widget.get_editable())
            note = next(widget for widget in views if widget.get_editable())
            source = next(widget for widget in widgets if isinstance(widget, Gtk.Entry))
            kind = next(widget for widget in widgets if isinstance(widget, Gtk.ComboBoxText))
            details = next(widget for widget in widgets if isinstance(widget, Gtk.Expander)
                           and widget.get_label().startswith('Add a note'))
            buttons['← Older'].clicked()
            details.set_expanded(True)
            note.get_buffer().set_text('Unsaved synthetic reflection for the older passage.')
            source.set_text('https://example.invalid/draft')
            kind.set_active_id('research')
            adjustment = reader.get_parent().get_vadjustment()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            adjustment.set_value(180)
            assert adjustment.get_value() == 180
            assert color(reader) == '#ddeeff'

            def verify():
                try:
                    photograph(window, 'reader-after.png')
                    result['computed_foreground'] = color(reader)
                    assert color(reader) == '#ffccaa', ('open reader kept the old palette', color(reader))
                    result['checks'].append('same-reader-overrides-cached-user-css-after-theme-change')
                    assert window in Gtk.Window.list_toplevels()
                    assert 'John 1:1' in content(reader)
                    assert adjustment.get_value() == 180
                    assert content(note) == 'Unsaved synthetic reflection for the older passage.'
                    assert source.get_text() == 'https://example.invalid/draft'
                    assert kind.get_active_id() == 'research'
                    result['checks'].append('selected-entry-scroll-draft-kind-and-source-preserved')
                    buttons['Newer →'].clicked()
                    assert content(note) == '' and source.get_text() == ''
                    buttons['← Older'].clicked()
                    assert content(note) == 'Unsaved synthetic reflection for the older passage.'
                    assert source.get_text() == 'https://example.invalid/draft'
                    assert kind.get_active_id() == 'research'
                    result['checks'].append('navigation-restores-the-unsaved-draft-after-theme-change')
                    assert database.read_bytes() == original_database
                    result['checks'].append('private-history-database-byte-identical')
                except BaseException:
                    result['failures'].append(traceback.format_exc())
                finally:
                    window.destroy()
                return GLib.SOURCE_REMOVE

            def switch():
                photograph(window, 'reader-before.png')
                (themes / 'current').write_text('cool')
                GLib.timeout_add(2600, verify)
                return GLib.SOURCE_REMOVE

            GLib.timeout_add(100, switch)
        except BaseException:
            result['failures'].append(traceback.format_exc())
            window.destroy()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(500, begin)
    run('/fixture/helper-never-executed', database)
    result['status'] = 'failed' if result['failures'] else 'passed'
    (output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return bool(result['failures'])


@unittest.skipUnless(shutil.which('Xvfb') and shutil.which('dbus-run-session'), 'Requires private GTK harness')
class HistoryThemeTests(unittest.TestCase):
    def test_open_reader_rethemes_without_losing_scroll_or_unsaved_material(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-history-theme-') as temporary:
            root = Path(temporary)
            env = dict(os.environ, GDK_BACKEND='x11', NO_AT_BRIDGE='1', GTK_USE_PORTAL='0',
                       PYTHONDONTWRITEBYTECODE='1')
            for key, name in (('HOME', 'home'), ('XDG_RUNTIME_DIR', 'run'), ('XDG_CONFIG_HOME', 'config'),
                              ('XDG_STATE_HOME', 'state'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
                path = root / name
                path.mkdir(mode=0o700)
                env[key] = str(path)
            for key in ('DISPLAY', 'SWAYSOCK', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
                env.pop(key, None)
            cached_css = root / 'config/gtk-3.0/gtk.css'
            cached_css.parent.mkdir()
            cached_css.write_text('#scripture-history, #scripture-history textview, '
                                  '#scripture-history textview text { color: #ddeeff; background-color: #202a30; }')
            bus_config = root / 'session-bus.conf'
            bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                                  '<auth>EXTERNAL</auth><policy context="default">'
                                  '<allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/>'
                                  '<allow own="*"/></policy></busconfig>')
            output = Path(os.environ.get('OLDBOOK_HISTORY_THEME_OUTPUT', root / 'evidence'))
            output.mkdir(parents=True, exist_ok=False)
            read_fd, write_fd = os.pipe()
            with (output / 'xvfb.log').open('w') as log:
                server = subprocess.Popen(['Xvfb', '-displayfd', str(write_fd), '-nolisten', 'tcp',
                                           '-screen', '0', '1200x900x24', '-ac'], env=env,
                                          pass_fds=(write_fd,), stdout=log, stderr=log)
                os.close(write_fd)
                try:
                    self.assertTrue(select.select([read_fd], [], [], 8)[0], 'Private Xvfb did not start')
                    display = os.read(read_fd, 64).decode().strip()
                    self.assertTrue(display.isdigit())
                    env['DISPLAY'] = ':' + display
                    result = subprocess.run(['dbus-run-session', '--config-file', str(bus_config),
                                             sys.executable, str(Path(__file__).resolve()),
                                             '--native-child', str(output)], env=env, capture_output=True,
                                            text=True, timeout=30)
                    (output / 'gtk.log').write_text(result.stdout + result.stderr)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(json.loads((output / 'evidence.json').read_text())['status'], 'passed')
                finally:
                    os.close(read_fd)
                    server.terminate()
                    server.wait(timeout=5)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--native-child':
        raise SystemExit(native_reader(Path(sys.argv[2])))
    unittest.main()
