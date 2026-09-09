"""Render swaync's real widget tree with the real stylesheet, offscreen."""
import sys, gi
from pathlib import Path
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

CSS = sys.argv[1]; OUT = sys.argv[2]
STATES = [('normal', False), ('normal', True), ('critical', False), ('low', False)]

provider = Gtk.CssProvider()
errs = []
provider.connect('parsing-error', lambda p, s, e: errs.append(e.message))
import re, tempfile
raw = Path(CSS).read_text()
raw = re.sub(r'(?ms)^:root\s*\{.*?\}\s*', '', raw)
lines = raw.splitlines(keepends=True)
dropped = []
for _ in range(40):
    tmp = tempfile.NamedTemporaryFile('w', suffix='.css', delete=False)
    tmp.write(''.join(lines)); tmp.close()
    try:
        provider.load_from_path(tmp.name); break
    except GLib.Error as exc:
        m = re.search(r':(\d+):\d+', exc.message)
        if not m: raise
        i = int(m.group(1)) - 1
        dropped.append(lines[i].strip()[:52]); lines[i] = '\n'
if dropped:
    print('swaync-only declarations skipped for this render:', len(dropped))
    for d in dropped[:4]: print('   ', d)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                         Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
if errs:
    print('CSS ERRORS:', errs[:3])

def card(urgency, hovered):
    row = Gtk.EventBox(); row.get_style_context().add_class('notification-row')
    bg = Gtk.EventBox(); bg.get_style_context().add_class('notification-background')
    note = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    ctx = note.get_style_context()
    ctx.add_class('notification'); ctx.add_class(urgency)
    if hovered:
        ctx.set_state(Gtk.StateFlags.PRELIGHT)
        row.get_style_context().set_state(Gtk.StateFlags.PRELIGHT)
    icon = Gtk.Label(label=''); icon.get_style_context().add_class('app-icon')
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    app = Gtk.Label(label='OLDBOOK', xalign=0); app.get_style_context().add_class('app-name')
    when = Gtk.Label(label='now', xalign=0); when.get_style_context().add_class('time')
    head.pack_start(app, False, False, 0); head.pack_start(when, False, False, 0)
    summary = Gtk.Label(label='Remote build finished', xalign=0)
    summary.get_style_context().add_class('summary')
    body = Gtk.Label(label='waybar 0.15.0-r4 built on bak and signed here.', xalign=0)
    body.get_style_context().add_class('body'); body.set_line_wrap(True)
    text.pack_start(head, False, False, 0); text.pack_start(summary, False, False, 0)
    text.pack_start(body, False, False, 0)
    close = Gtk.Button(label='×')
    close.get_style_context().add_class('close-button')
    close.set_valign(Gtk.Align.START)
    note.pack_start(icon, False, False, 0)
    note.pack_start(text, True, True, 0)
    note.pack_start(close, False, False, 0)
    bg.add(note); row.add(bg)
    row.set_size_request(430, -1)
    return row

outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
outer.get_style_context().add_class('floating-notifications')
for urgency, hovered in STATES:
    outer.pack_start(card(urgency, hovered), False, False, 0)

win = Gtk.OffscreenWindow()
win.set_app_paintable(True)
frame = Gtk.Box(); frame.set_border_width(26)
frame.add(outer); win.add(frame)
win.show_all()
while Gtk.events_pending():
    Gtk.main_iteration()
pb = win.get_pixbuf()
w, h = pb.get_width(), pb.get_height()
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
cr = cairo.Context(surf)
# A painting-ish ground so the card's own light is visible against something.
grad = cairo.LinearGradient(0, 0, w, h)
grad.add_color_stop_rgb(0, 0.20, 0.26, 0.36)
grad.add_color_stop_rgb(1, 0.34, 0.27, 0.22)
cr.set_source(grad); cr.paint()
Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0); cr.paint()
surf.write_to_png(OUT)
print('rendered', w, 'x', h, '->', OUT)
