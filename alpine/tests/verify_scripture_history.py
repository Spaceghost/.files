#!/usr/bin/env python3
"""Exercise history reader controls under the private GTK verification harness."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import scripture_history as history
from scripture_history_reader import run


def main():
    if os.environ.get('MBP_INTEL_STRATA_GTK_PRIVATE_BUS') != '1' or os.environ.get('GDK_BACKEND') != 'x11':
        raise RuntimeError('Run this fixture through the private Xvfb/D-Bus GTK harness')
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    output = Path(os.environ['MBP_INTEL_SCRIPTURE_HISTORY_VERIFY_OUTPUT'])
    output.mkdir(parents=True, exist_ok=False)
    database = history.database_path()
    for number in (1, 2):
        history.select({'kind': 'study-note', 'reference': f'John 1:{number}',
                        'text': f'Private full passage {number}', 'title': 'Private study fixture',
                        'reflection': '\n'.join(f'Complete study line {line}' for line in range(55)),
                        'sources': [{'title': 'Private source', 'license': 'Fixture license',
                                     'text': 'Complete source excerpt', 'url': 'https://example.invalid/source'}],
                        'provenance': {'method': 'fixture; no model or network request'}},
                       database, now=number)
    checks, failures = [], []

    def walk(widget):
        yield widget
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                yield from walk(child)

    def verify():
        windows = [window for window in Gtk.Window.list_toplevels() if window.get_title() == 'Scripture history']
        if not windows:
            return GLib.SOURCE_CONTINUE
        window = windows[0]
        try:
            widgets = list(walk(window))
            buttons = {widget.get_label(): widget for widget in widgets if isinstance(widget, Gtk.Button)}
            textviews = [widget for widget in widgets if isinstance(widget, Gtk.TextView)]
            reader = next(widget for widget in textviews if not widget.get_editable())
            note = next(widget for widget in textviews if widget.get_editable())
            source = next(widget for widget in widgets if isinstance(widget, Gtk.Entry))
            def text():
                buffer = reader.get_buffer()
                return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
            assert 'John 1:2' in text()
            checks.append('opens-latest-complete-entry')
            buttons['← Older'].clicked()
            assert 'John 1:1' in text() and 'Complete source excerpt' in text()
            assert 'Fixture license' in text() and 'no model or network' in text()
            checks.append('older-entry-retains-study-sources-license-provenance')
            scroll = reader.get_parent()
            adjustment = scroll.get_vadjustment()
            assert adjustment.get_upper() > adjustment.get_page_size()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            checks.append('full-material-scrolls-beyond-viewport')
            note.get_buffer().set_text('Private appended note, linked to the first entry.')
            source.set_text('https://example.invalid/first-entry-note')
            buttons['Newer →'].clicked()
            assert note.get_buffer().get_char_count() == 0 and source.get_text() == ''
            buttons['← Older'].clicked()
            assert note.get_buffer().get_char_count() > 0
            assert source.get_text() == 'https://example.invalid/first-entry-note'
            checks.append('unsaved-note-and-source-stay-with-original-entry-during-navigation')
            buttons['Save additional material'].clicked()
            assert history.get(1, database)['additions'][0]['document']['text'].startswith('Private appended note')
            assert 'Private appended note' in text()
            checks.append('note-button-appends-to-viewed-entry')
            buttons['Newer →'].clicked()
            assert 'John 1:2' in text() and 'Private appended note' not in text()
            assert not buttons['Newer →'].get_sensitive()
            checks.append('newer-navigation-does-not-move-notes')
            buttons['← Older'].clicked()
            checks.append('history-remains-readable-after-appending')
            adjustment.set_value(0)
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            def photograph(name):
                allocation = window.get_allocation()
                picture = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                                    allocation.width, allocation.height)
                picture.savev(str(output / name), 'png', [], [])
            photograph('history-reader.png')
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            photograph('history-attribution.png')
        except BaseException:
            failures.append(traceback.format_exc())
        finally:
            window.destroy()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(500, verify)
    result = run(REPO / 'alpine/desktop/.local/bin/mbp-intel-scripture', database)
    record = {'status': 'failed' if failures else 'passed', 'checks': checks, 'failures': failures,
              'isolation': 'private Xvfb, D-Bus, HOME and XDG data; synthetic content only',
              'network_or_model_calls': 0,
              'source_sha256': {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest()
                                for name in ('alpine/desktop/.local/lib/mbp_intel/scripture_history.py',
                                             'alpine/desktop/.local/lib/mbp_intel/scripture_history_reader.py')}}
    (output / 'evidence.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return 1 if failures else result


if __name__ == '__main__':
    sys.exit(main())
