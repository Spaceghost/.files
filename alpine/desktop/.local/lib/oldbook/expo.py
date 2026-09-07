"""On-demand workspace overview; all navigation uses Sway container identities."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import socket
import sys


def walk(node):
    yield node
    for child in node.get('nodes', []) + node.get('floating_nodes', []):
        yield from walk(child)


def workspace_cards(tree):
    cards = {num: {'num': num, 'name': f'{num}:STRATA' if num == 6 else f'Desktop {num}',
                   'windows': [], 'rect': {'x': 0, 'y': 0, 'width': 1440, 'height': 900}}
             for num in range(1, 11)}
    for node in walk(tree):
        if node.get('type') != 'workspace' or node.get('num', -1) < 0:
            continue
        windows = [view for view in walk(node) if view.get('app_id') or view.get('window')]
        cards[node['num']] = dict(node, windows=windows)
    return [cards[num] for num in sorted(cards)]


def focus_command(target):
    if 'id' in target:
        return f'[con_id={int(target["id"])}] focus'
    return f'workspace number {int(target["num"])}'


def miniature_rect(rect, workspace, width, height):
    scale = min(width / max(1, workspace.get('width', width)),
                height / max(1, workspace.get('height', height)))
    w = min(width, max(48, int(rect.get('width', 200) * scale)))
    h = min(height, max(30, int(rect.get('height', 150) * scale)))
    x = min(width - w, max(0, int((rect.get('x', 0) - workspace.get('x', 0)) * scale)))
    y = min(height - h, max(0, int((rect.get('y', 0) - workspace.get('y', 0)) * scale)))
    return x, y, w, h


def main(action='toggle'):
    ipc = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'bin/oldbook-workspaces'))
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    sway = ipc['find_socket'](runtime)
    directory = ipc['prepare_directory'](runtime).parent
    identity = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
    address = directory / ('expo-' + identity + '.sock')
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        try:
            client.sendto(action.encode(), str(address))
            return
        except (FileNotFoundError, ConnectionRefusedError):
            if action == 'close':
                return
    with (directory / ('expo-' + identity + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        address.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(address))
            try:
                show(ipc, sway, control)
            finally:
                address.unlink(missing_ok=True)


def show(ipc, sway, control):
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import Gtk, Gdk, GLib, Pango, GtkLayerShell

    window = Gtk.Window(title='Ghost Expo')
    window.set_name('ghost-expo')
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, 'oldbook-expo')
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
    GtkLayerShell.set_exclusive_zone(window, -1)
    for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                 GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
        GtkLayerShell.set_anchor(window, edge, True)
    outputs = ipc['request'](sway, 3)
    focused = next((o.get('rect') for o in outputs if o.get('focused')), None)
    display = Gdk.Display.get_default()
    for index in range(display.get_n_monitors()):
        monitor = display.get_monitor(index)
        geometry = monitor.get_geometry()
        if focused and geometry.x == focused['x'] and geometry.y == focused['y']:
            GtkLayerShell.set_monitor(window, monitor)
            break
    css = Gtk.CssProvider()
    css.load_from_data(b'''
#ghost-expo { background: rgba(24, 23, 29, 0.97); color: #ebdbb2; }
#expo-title { font: bold 28px sans-serif; color: #d8b879; }
#expo-hint { color: #b7a9c6; }
#ghost-expo entry { background: #302b36; color: #ebdbb2; border: 1px solid #645373; border-radius: 8px; padding: 10px; }
#ghost-expo .workspace { background: #26232c; border: 1px solid #51435e; border-radius: 10px; padding: 10px; }
#ghost-expo .active { border-color: #d8b879; }
#ghost-expo button { background: #342e3d; color: #ebdbb2; border: 1px solid #635370; border-radius: 6px; padding: 5px; }
#ghost-expo button:hover, #ghost-expo button:focus { background: #52405f; border-color: #d8b879; }
#ghost-expo .workspace-title { font-weight: bold; background: transparent; border: 0; }
''')
    Gtk.StyleContext.add_provider_for_screen(window.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    root.set_border_width(28)
    window.add(root)
    heading = Gtk.Box(spacing=12)
    title = Gtk.Label(label='EXPO', xalign=0)
    title.set_name('expo-title')
    heading.pack_start(title, True, True, 0)
    close = Gtk.Button(label='Close · Esc')
    close.connect('clicked', lambda *_: Gtk.main_quit())
    heading.pack_end(close, False, False, 0)
    root.pack_start(heading, False, False, 0)
    hint = Gtk.Label(label='Choose a window or desktop · 3/4 fingers down to close · 1–9 / 0 jump to desktop', xalign=0)
    hint.set_name('expo-hint')
    root.pack_start(hint, False, False, 0)
    search = Gtk.SearchEntry(placeholder_text='Find a window, app, or workspace…')
    root.pack_start(search, False, False, 0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    root.pack_start(scroll, True, True, 0)
    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_homogeneous(True)
    flow.set_min_children_per_line(1)
    flow.set_max_children_per_line(4)
    flow.set_row_spacing(14)
    flow.set_column_spacing(14)
    scroll.add(flow)
    targets = []
    fingerprint = None

    def select_target(target):
        ipc['command'](sway, focus_command(target))
        Gtk.main_quit()

    def button(text, target):
        item = Gtk.Button()
        label = Gtk.Label(label=text)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(28)
        item.add(label)
        item.set_tooltip_text(text)
        item.connect('clicked', lambda *_: select_target(target))
        return item

    def refresh(force=False):
        nonlocal fingerprint
        try:
            tree = ipc['request'](sway, 4)
        except (OSError, RuntimeError):
            Gtk.main_quit()
            return False
        query = search.get_text().casefold()
        current = json.dumps(tree, sort_keys=True) + query
        if current == fingerprint and not force:
            return True
        fingerprint = current
        targets.clear()
        for child in flow.get_children():
            flow.remove(child)
        for card in workspace_cards(tree):
            windows = card['windows']
            text = card['name'] + ' ' + ' '.join(str(w.get('name', '')) + ' ' + str(w.get('app_id', '')) for w in windows)
            if query and query not in text.casefold():
                continue
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.get_style_context().add_class('workspace')
            if card.get('focused') or any(w.get('focused') for w in windows):
                box.get_style_context().add_class('active')
            count = str(len(windows)) + (' window' if len(windows) == 1 else ' windows')
            title_button = button(card['name'] + '  ·  ' + count, {'num': card['num']})
            title_button.get_style_context().add_class('workspace-title')
            box.pack_start(title_button, False, False, 0)
            miniature = Gtk.Fixed()
            miniature.set_size_request(280, 155)
            for view in windows:
                item = button(str(view.get('name') or view.get('app_id') or 'Window'), view)
                x, y, width, height = miniature_rect(view.get('rect', {}), card['rect'], 280, 155)
                item.set_size_request(width, height)
                miniature.put(item, x, y)
                if query and query in (str(view.get('name', '')) + ' ' + str(view.get('app_id', ''))).casefold():
                    targets.append(view)
            if not windows:
                label = Gtk.Label(label='Empty desktop')
                miniature.put(label, 82, 65)
            box.pack_start(miniature, True, True, 0)
            flow.add(box)
            targets.append({'num': card['num']})
        flow.show_all()
        return True

    def keypress(_, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and search.has_focus():
            activate_search()
            return True
        if not search.get_text() and Gdk.KEY_0 <= event.keyval <= Gdk.KEY_9:
            select_target({'num': (event.keyval - Gdk.KEY_0) or 10})
            return True
        return False

    swipe = [0.0, 0.0]
    def gesture(_, event):
        if event.type != Gdk.EventType.TOUCHPAD_SWIPE:
            return False
        data = event.touchpad_swipe
        if data.n_fingers not in (3, 4):
            return False
        if data.phase == Gdk.TouchpadGesturePhase.BEGIN:
            swipe[:] = [0.0, 0.0]
        elif data.phase == Gdk.TouchpadGesturePhase.UPDATE:
            swipe[0] += data.dx
            swipe[1] += data.dy
        elif data.phase == Gdk.TouchpadGesturePhase.END:
            if swipe[1] > 40 and abs(swipe[1]) > abs(swipe[0]):
                Gtk.main_quit()
            elif abs(swipe[0]) > 60 and abs(swipe[0]) > abs(swipe[1]):
                ipc['command'](sway, 'workspace next' if swipe[0] < 0 else 'workspace prev')
                Gtk.main_quit()
        return True

    def incoming(*_):
        action = control.recv(32).decode()
        if action in ('toggle', 'close'):
            Gtk.main_quit()
        return True

    def activate_search(*_):
        refresh(True)
        if targets:
            select_target(targets[0])

    window.add_events(Gdk.EventMask.TOUCHPAD_GESTURE_MASK)
    window.connect('event', gesture)
    window.connect('key-press-event', keypress)
    window.connect('destroy', lambda *_: Gtk.main_quit() if Gtk.main_level() else None)
    search.connect('key-press-event', keypress)
    search.connect('search-changed', lambda *_: refresh(True))
    search.connect('activate', activate_search)
    GLib.io_add_watch(control.fileno(), GLib.IO_IN, incoming)
    GLib.timeout_add(1000, refresh)
    refresh()
    window.show_all()
    search.grab_focus()
    Gtk.main()
    window.destroy()
