import ast
import cProfile
import hashlib
import io
import json
import pathlib
import pstats
import runpy
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, Gdk, GLib, Gio, GtkLayerShell, Pango

root = pathlib.Path('/home/jack/.files')
source = root / 'alpine/desktop/.local/bin/oldbook-decoration'
namespace = runpy.run_path(str(source))
module = ast.parse(source.read_text())
daemon = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'daemon')
caption = next(n for n in daemon.body if isinstance(n, ast.ClassDef) and n.name == 'Caption')
namespace.update(Gtk=Gtk, Gdk=Gdk, GLib=GLib, Gio=Gio,
                 GtkLayerShell=GtkLayerShell, Pango=Pango, retired=set())
exec(compile(ast.Module(body=[caption], type_ignores=[]), str(source), 'exec'), namespace)
Caption = namespace['Caption']
monitor = Gdk.Display.get_default().get_monitor(0)
style = namespace['appearance']()
outrect = {'x': 0, 'y': 0, 'width': 1440, 'height': 900}
original_show = Gtk.Window.show
Gtk.Window.show = lambda self: None
calls = []

for name in ['__init__', 'update', 'restyle', 'place', 'destroy']:
    original = getattr(Caption, name)

    def observe(self, *args, _original=original, _name=name, **kwargs):
        wall = time.perf_counter()
        cpu = time.process_time()
        try:
            return _original(self, *args, **kwargs)
        finally:
            calls.append({'method': _name,
                          'wall_ms': round((time.perf_counter() - wall) * 1000, 3),
                          'cpu_ms': round((time.process_time() - cpu) * 1000, 3)})

    setattr(Caption, name, observe)

profile = cProfile.Profile()
profile.enable()
objects = []
try:
    for index in range(12):
        placement = {
            'mode': 'window', 'edge': 'bottom', 'square': False, 'window_id': index + 1,
            'rect': {'x': 200 if index % 2 == 0 else 900,
                     'y': 160 if index % 2 == 0 else 120,
                     'width': 620 if index % 2 == 0 else 420,
                     'height': 360 if index % 2 == 0 else 280}}
        app = 'attachment-floating' if index % 2 == 0 else 'attachment-hover'
        context = {'id': index + 1, 'title': 'Synthetic caption fixture', 'app': app,
                   'workspace': '1', 'floating': True, 'fullscreen': False,
                   'node': {'app_id': app}}
        item = Caption(monitor, placement, False)
        objects.append(item)
        item.update(context, {}, style, placement, outrect)
        assert not item.window.get_mapped()
        item.destroy()
        objects.remove(item)
finally:
    for item in objects:
        item.destroy()
    profile.disable()
    Gtk.Window.show = original_show

out = root / 'alpine/verification/animation-fluidity/decoration/construction-profile'
out.mkdir(parents=True, exist_ok=True)
stream = io.StringIO()
pstats.Stats(profile, stream=stream).sort_stats('cumulative').print_stats(40)
(out / 'profile.txt').write_text(stream.getvalue())
evidence = {
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'isolation': 'Synthetic contexts; GTK3 widgets constructed and measured with '
                 'Gtk.Window.show suppressed. No mapped toplevels or gesture/restart commands.',
    'calls': calls}
(out / 'measurements.json').write_text(json.dumps(evidence, indent=2) + '\n')
(out / 'probe.py').write_bytes(pathlib.Path(__file__).read_bytes())
print(stream.getvalue())
print(json.dumps(calls, indent=2))
