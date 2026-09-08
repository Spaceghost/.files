"""Slide the focused workspace's windows off screen, and slide them back in place.

The windows themselves are never moved.  A lossless capture of the output is
replayed as one card per visible window in a layer-shell overlay, and the real
workspace is swapped for an empty one behind that overlay while it covers the
screen.  Restoring swaps the workspace back at the moment the cards land, so the
handover happens on a frame where the overlay is opaque over every window.
"""
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import socket
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workspace_model import (addressable_name, displayed_views, fullscreen_nodes,
                             workspace_name, workspace_nodes)

STATE_VERSION = 1
HIDDEN_WORKSPACE = 'desktop'
# Holds the one display-wide stylesheet the helper installs.
STYLE_INSTALLED = []

# Slide to edges, refined: straight out of the nearest edge, staggered top-left
# first, with the scale and blur a plain slide does not have.
OUT_MS = 340.0
IN_MS = 300.0
STAGGER_MS = 30.0
STAGGER_BUDGET_MS = 120.0
SCALE_END = 0.88
BLUR_END = 4.0
CLEARANCE = 80.0
# A card leaving accelerates away; a card arriving eases into its place.
EXIT_CURVE = ((0.4, 0.0), (1.0, 1.0))
RETURN_CURVE = ((0.0, 0.0), (0.2, 1.0))
PRESENT_TIMEOUT_MS = 150.0

# Matches swayfx corner_radius and the shadow_* settings in swayfx/effects.conf,
# so a card is indistinguishable from the window it stands in for.
CORNER_RADIUS = 6.0
SHADOW_COLOR = '#1d2021c0'
SHADOW_OFFSET = (0.0, 6.0)
SHADOW_RADIUS = 24.0


def parse_ppm(data):
    """Return (width, height, pixel offset) for a binary P6 portable pixmap."""
    fields, index = [], 0
    while len(fields) < 4:
        while index < len(data) and data[index:index + 1].isspace():
            index += 1
        if data[index:index + 1] == b'#':
            while index < len(data) and data[index:index + 1] != b'\n':
                index += 1
            continue
        start = index
        while index < len(data) and not data[index:index + 1].isspace():
            index += 1
        if start == index:
            raise ValueError('truncated PPM header')
        fields.append(data[start:index])
    if fields[0] != b'P6' or fields[3] != b'255':
        raise ValueError('unsupported PPM format')
    width, height, offset = int(fields[1]), int(fields[2]), index + 1
    if width <= 0 or height <= 0 or len(data) - offset < width * height * 3:
        raise ValueError('truncated PPM pixel data')
    return width, height, offset


def intersect(rect, bounds):
    left = max(rect.get('x', 0), bounds['x'])
    top = max(rect.get('y', 0), bounds['y'])
    right = min(rect.get('x', 0) + rect.get('width', 0), bounds['x'] + bounds['width'])
    bottom = min(rect.get('y', 0) + rect.get('height', 0), bounds['y'] + bounds['height'])
    return {'x': left, 'y': top, 'width': max(0, right - left), 'height': max(0, bottom - top)}


def visible_views(workspace):
    """Return the views the compositor is actually drawing, in stacking order."""
    covering = fullscreen_nodes(workspace)
    if covering:
        return [view for node in covering for view in displayed_views(node)]
    return displayed_views(workspace)


def cards_for(workspace, bounds):
    """Return output-local card rectangles for every window worth animating.

    Sticky windows follow the workspace swap and stay on screen by themselves,
    so replaying them as cards would draw them twice.
    """
    cards = []
    for view in visible_views(workspace):
        if view.get('sticky'):
            continue
        clipped = intersect(view.get('rect', {}), bounds)
        if clipped['width'] <= 0 or clipped['height'] <= 0:
            continue
        cards.append({'x': clipped['x'] - bounds['x'], 'y': clipped['y'] - bounds['y'],
                      'width': clipped['width'], 'height': clipped['height']})
    return cards


def crop_bounds(card, scale, pixel_width, pixel_height):
    """Return the capture pixel rectangle covering a card's logical rectangle."""
    left = max(0, min(pixel_width, round(card['x'] * scale)))
    top = max(0, min(pixel_height, round(card['y'] * scale)))
    right = max(left, min(pixel_width, round((card['x'] + card['width']) * scale)))
    bottom = max(top, min(pixel_height, round((card['y'] + card['height']) * scale)))
    return left, top, right - left, bottom - top


def crop_rows(data, offset, stride, box):
    """Copy one card's pixels out of the capture into a tightly packed buffer.

    A window that spans the full width of the output — most of them — is already
    contiguous in the capture and needs one copy rather than one per row.
    """
    left, top, width, height = box
    start = offset + top * stride + left * 3
    span = width * 3
    if span == stride:
        return bytes(data[start:start + span * height])
    pixels = bytearray(span * height)
    source = memoryview(data)
    for row in range(height):
        begin = start + row * stride
        pixels[row * span:(row + 1) * span] = source[begin:begin + span]
    return bytes(pixels)


def exit_vector(card, width, height):
    """Return the offset that carries a card clear of its nearest output edge."""
    center_x = card['x'] + card['width'] / 2
    center_y = card['y'] + card['height'] / 2
    distances = ((center_x, 'left'), (width - center_x, 'right'),
                 (center_y, 'top'), (height - center_y, 'bottom'))
    edge = min(distances, key=lambda item: item[0])[1]
    if edge == 'left':
        return -(card['x'] + card['width'] + CLEARANCE), 0.0
    if edge == 'right':
        return width - card['x'] + CLEARANCE, 0.0
    if edge == 'top':
        return 0.0, -(card['y'] + card['height'] + CLEARANCE)
    return 0.0, height - card['y'] + CLEARANCE


def stagger_order(cards):
    """Return each card's launch slot, top-left first, keyed by draw index."""
    ranked = sorted(range(len(cards)), key=lambda index: (cards[index]['y'] + cards[index]['x'],
                                                          cards[index]['y'], index))
    slots = [0] * len(cards)
    for slot, index in enumerate(ranked):
        slots[index] = slot
    return slots


def stagger_step(count):
    if count < 2:
        return 0.0
    return min(STAGGER_MS, STAGGER_BUDGET_MS / (count - 1))


def sequence_ms(count, duration):
    return duration + stagger_step(count) * max(0, count - 1)


def bezier(first, second, value):
    """Evaluate a CSS-style cubic-bezier(x1, y1, x2, y2) easing at `value`.

    Both control points share the shape `(x, y)`, and the curve runs from (0, 0)
    to (1, 1).  The x coordinate has to be inverted to find the parameter, which
    Newton's method resolves in a couple of steps for these gentle curves.
    """
    first_x, first_y = first
    second_x, second_y = second

    def axis(start, end, parameter):
        inverse = 1 - parameter
        return (3 * inverse * inverse * parameter * start
                + 3 * inverse * parameter * parameter * end + parameter ** 3)

    parameter = value
    for _ in range(6):
        error = axis(first_x, second_x, parameter) - value
        slope = (axis(first_x, second_x, parameter + 1e-4)
                 - axis(first_x, second_x, parameter - 1e-4)) / 2e-4
        if abs(error) < 1e-5 or slope <= 1e-6:
            break
        parameter = min(1.0, max(0.0, parameter - error / slope))
    return axis(first_y, second_y, parameter)


def travel_at(slot, count, elapsed, duration, restoring):
    """Return how far along its exit path a card sits, 0 at rest and 1 clear.

    Leaving accelerates and arriving decelerates, which is what makes the two
    directions read as one movement rather than as a symmetrical slide that
    slows down at the very moment a card should be whipping off the screen.
    """
    progress = (elapsed - slot * stagger_step(count)) / duration
    progress = min(1.0, max(0.0, progress))
    if restoring:
        return 1.0 - bezier(*RETURN_CURVE, progress)
    return bezier(*EXIT_CURVE, progress)


def switch_command(workspace):
    number = workspace.get('num', -1)
    if isinstance(number, int) and number >= 0:
        return 'workspace number ' + json.dumps(workspace_name(number))
    # A renamed workspace cannot be addressed by its captured name; Sway still
    # remembers where the hidden workspace was entered from.
    return 'workspace back_and_forth'


def private_directory(runtime):
    path = runtime / 'mbp-intel' / 'showdesktop'
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError(f'unsafe runtime directory: {path}')
    return path


def read_state(directory):
    try:
        state = json.loads((directory / 'state.json').read_text())
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) and state.get('version') == STATE_VERSION else {}


def write_state(directory, state):
    path = directory / 'state.json'
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def clear_state(directory):
    # The capture is a picture of the user's screen; it never outlives the swap.
    (directory / 'state.json').unlink(missing_ok=True)
    (directory / 'capture.ppm').unlink(missing_ok=True)


def capture(output_name, destination):
    """Write a lossless capture of one output.  PPM keeps this under a frame."""
    subprocess.run(['grim', '-o', output_name, '-t', 'ppm', str(destination)],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, timeout=5)
    os.chmod(destination, 0o600)


def load_ipc():
    return runpy.run_path(str(Path(__file__).resolve().parents[2] / 'bin/mbp-intel-workspaces'))


def focused_workspace(ipc, sway):
    for workspace in ipc['request'](sway, 1):
        if workspace.get('focused'):
            return workspace
    raise RuntimeError('no focused workspace')


def output_rect(ipc, sway, name):
    for output in ipc['request'](sway, 3):
        if output.get('name') == name and output.get('active'):
            return output['rect']
    raise RuntimeError(f'output not available: {name}')


def workspace_tree(ipc, sway, name):
    for workspace in workspace_nodes(ipc['request'](sway, 4)):
        if workspace.get('name') == name:
            return workspace
    raise RuntimeError(f'workspace not in tree: {name}')


def plan_show(ipc, sway):
    """Return the capture plan for the focused workspace, or None if bare."""
    workspace = focused_workspace(ipc, sway)
    if workspace.get('name') == HIDDEN_WORKSPACE:
        return None
    bounds = output_rect(ipc, sway, workspace['output'])
    cards = cards_for(workspace_tree(ipc, sway, workspace['name']), bounds)
    if not cards:
        return None
    return {'version': STATE_VERSION, 'socket': str(sway), 'output': workspace['output'],
            'workspace': workspace['name'], 'restore': switch_command(workspace),
            'workspace_id': workspace['id'], 'workspace_num': workspace['num'], 'hidden': False,
            'width': bounds['width'], 'height': bounds['height'], 'cards': cards,
            'created_at': time.time()}


def exact_switch(workspace):
    """Keep a requested custom name even if an empty workspace is recreated."""
    name = workspace['name']
    if not addressable_name(name):
        raise ValueError('workspace name cannot be addressed safely')
    return 'workspace ' + json.dumps(name, ensure_ascii=False)


def origin_workspace(workspaces, state):
    if 'workspace_id' in state:
        return next((item for item in workspaces if item['id'] == state['workspace_id']), None)
    # Read captures left by the previous helper without using back_and_forth,
    # whose destination changes as soon as the user navigates somewhere else.
    number = state.get('workspace', '').partition(':')[0]
    return next((item for item in workspaces if item['name'] == state.get('workspace')
                 or (number.isdecimal() and item.get('num') == int(number))), None)


def has_hidden_windows(ipc, sway, state):
    origin = origin_workspace(workspace_nodes(ipc['request'](sway, 4)), state)
    return bool(origin and any(not view.get('sticky') for view in visible_views(origin)))


def recover_state(ipc, sway, directory):
    """Release a hidden session while retaining any external destination."""
    state = read_state(directory)
    if not state:
        clear_state(directory)
        return
    released = False
    try:
        if state.get('socket') != str(sway):
            released = True
            return
        workspaces = ipc['request'](sway, 1)
        current = next((item for item in workspaces if item.get('focused')), None)
        hidden = next((item for item in workspaces if item['name'] == HIDDEN_WORKSPACE
                       and item.get('visible') and item.get('output') == state.get('output')), None)
        if not current or not hidden:
            # Windows are still on their original workspace. Keeping the
            # requested destination avoids destroying an empty workspace.
            released = True
            return
        origin = origin_workspace(workspaces, state)
        if origin is not None:
            restore = exact_switch(origin)
        else:
            number = state.get('workspace_num', 1)
            restore = switch_command({'num': number if isinstance(number, int) and number >= 0 else 1})
        commands = [restore]
        if current['id'] != hidden['id']:
            # On another output the destination remains visible during this
            # detour, so even an empty custom workspace retains its identity.
            commands.append(exact_switch(current))
        ipc['command'](sway, '; '.join(commands))
        released = True
    finally:
        if released:
            clear_state(directory)


def launch_carousel():
    from ui_command import send_command
    if send_command('carousel', 'show'):
        return
    subprocess.Popen([str(Path.home() / '.local/bin/mbp-intel-carousel'), 'show'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     start_new_session=True)


class DesktopSession:
    """Distinguish our own swaps from navigation inside GTK's nested loop."""
    def __init__(self, ipc, sway, directory):
        self.ipc, self.sway, self.directory = ipc, sway, directory
        self.active = False
        self.expected = []
        self.cancel = None
        self.cancelled = False
        self.navigation = False

    def expect(self, target):
        self.expected.append(target)

    def focused(self, current):
        if self.expected:
            expected = self.expected[0]
            if (current.get('id') == expected.get('id') if 'id' in expected
                    else current.get('name') == expected.get('name')):
                self.expected.pop(0)
                return
        state = read_state(self.directory)
        if not state or state.get('socket') != str(self.sway):
            return
        if current.get('name') == HIDDEN_WORKSPACE:
            return
        if (self.active and not state.get('hidden')
                and current.get('id') == state.get('workspace_id')):
            return
        self.navigation = self.cancelled = True
        if self.cancel:
            self.cancel()
        if not self.active:
            self.finish()

    def finish(self):
        if self.navigation:
            try:
                recover_state(self.ipc, self.sway, self.directory)
            finally:
                self.navigation = False
                self.expected.clear()

    def swap(self, text, target):
        if self.cancelled:
            return False
        self.expect(target)
        try:
            self.ipc['command'](self.sway, text)
        except BaseException:
            self.expected.pop()
            raise
        return True


def session_socket(runtime):
    """Resolve the Sway socket without paying for the shared IPC module."""
    given = os.environ.get('SWAYSOCK')
    if given:
        path = Path(given)
        if path.is_socket() and path.stat().st_uid == os.getuid():
            return path
    return load_ipc()['find_socket'](runtime)


def control_address(directory, sway):
    identity = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
    return directory / ('control-' + identity + '.sock')


def deliver(address, action):
    """Hand the gesture to the warm helper.  False means none is listening."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        try:
            client.sendto(action.encode(), str(address))
            return True
        except OSError:
            return False


def warm_up():
    """Load the toolkit up front so a swipe never waits for an interpreter.

    Importing GTK and initialising it costs a third of a second, which is most
    of the delay between the swipe and the first frame of movement.  The helper
    pays that once at login instead of on every gesture.
    """
    preload_layer_shell()
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    Gtk.init()


def daemon():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    ipc = load_ipc()
    sway = ipc['find_socket'](runtime)
    directory = private_directory(runtime)
    address = control_address(directory, sway)
    # The lock is named for the session, so a helper left over from a previous
    # Sway socket can never keep this one from starting.
    with (directory / (address.stem + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        address.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(address))
            os.chmod(address, 0o600)
            try:
                serve(ipc, sway, directory, control)
            finally:
                address.unlink(missing_ok=True)


def serve(ipc, sway, directory, control):
    recover_state(ipc, sway, directory)
    warm_up()
    from ui_priority import request_priority
    request_priority()
    from gi.repository import GLib

    loop = GLib.MainLoop()
    session = DesktopSession(ipc, sway, directory)
    pending = {'action': None, 'stopping': False}

    def run_action(action):
        session.active = True
        session.cancelled = False
        try:
            perform(action, ipc, sway, directory, session)
        except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print(f'mbp-intel-showdesktop: {error}', file=sys.stderr, flush=True)
        finally:
            session.active = False
            session.cancel = None
            try:
                session.finish()
            except (KeyError, OSError, ValueError, RuntimeError) as error:
                print(f'mbp-intel-showdesktop: {error}', file=sys.stderr, flush=True)
            session.expected.clear()
        if pending['action'] and not pending['stopping']:
            action, pending['action'] = pending['action'], None
            GLib.idle_add(lambda: (run_action(action), GLib.SOURCE_REMOVE)[1],
                          priority=GLib.PRIORITY_HIGH_IDLE)

    def gesture(fd, condition):
        try:
            action = control.recv(32).decode('ascii', 'replace')
        except OSError:
            return GLib.SOURCE_CONTINUE
        if action not in ('show', 'restore', 'toggle', 'restore-or-carousel'):
            return GLib.SOURCE_CONTINUE
        if session.active:
            # A returning swipe during the outward pass means restore these
            # windows, even if another action cancels that pass before it ends.
            if action in ('restore', 'restore-or-carousel'):
                pending['action'] = 'restore'
        else:
            run_action(action)
        return GLib.SOURCE_CONTINUE

    def stop():
        pending['stopping'] = True
        session.cancelled = True
        if session.cancel:
            session.cancel()
        loop.quit()
        return GLib.SOURCE_REMOVE

    def event(fd, condition):
        if condition & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            return stop()
        try:
            kind, message = ipc['receive'](subscription)
            if kind == (1 << 31) | 6:
                return stop()
            if kind == (1 << 31) and message.get('change') == 'focus' and message.get('current'):
                session.focused(message['current'])
        except (KeyError, OSError, ValueError, RuntimeError) as error:
            print(f'mbp-intel-showdesktop: {error}', file=sys.stderr, flush=True)
            return stop()
        return GLib.SOURCE_CONTINUE

    subscription = socket.socket(socket.AF_UNIX)
    subscription.settimeout(3)
    subscription.connect(str(sway))
    ipc['send'](subscription, 2, '["workspace","shutdown"]')
    _, accepted = ipc['receive'](subscription)
    if not accepted.get('success'):
        raise RuntimeError('Sway rejected the workspace subscription')
    with subscription:
        sources = [GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, control.fileno(),
                                        GLib.IOCondition.IN, gesture),
                   GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, subscription.fileno(),
                                        GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR, event),
                   GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop),
                   GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, stop)]
        try:
            loop.run()
        finally:
            for identifier in sources:
                source = GLib.MainContext.default().find_source_by_id(identifier)
                if source:
                    source.destroy()
            try:
                recover_state(ipc, sway, directory)
            except (KeyError, OSError, ValueError, RuntimeError):
                clear_state(directory)


def run(action):
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    directory = private_directory(runtime)
    sway = session_socket(runtime)
    if deliver(control_address(directory, sway), action):
        return
    # A hidden workspace needs the focus guard even when the warm login helper
    # was stopped. Start its replacement before allowing another hide.
    state = read_state(directory)
    if (action == 'restore-or-carousel' and state.get('socket') == str(sway)
            and has_hidden_windows(load_ipc(), sway, state)):
        # Startup recovery will already unhide these windows. This same swipe
        # must not then open the carousel as though it began on a bare desktop.
        action = 'restore'
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[2] /
                              'bin/mbp-intel-showdesktop'), 'daemon'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if deliver(control_address(directory, sway), action):
            return
        if child.poll() not in (None, 0):
            break
        time.sleep(.025)
    raise RuntimeError('show-desktop helper did not become available')


def perform(action, ipc, sway, directory, session=None):
    with (directory / 'gesture.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # A swipe landed mid-animation; the running pass owns the screen.
            return
        state = read_state(directory)
        hidden = focused_workspace(ipc, sway).get('name') == HIDDEN_WORKSPACE
        if state and (not hidden or state.get('socket') != str(sway)):
            recover_state(ipc, sway, directory)
            state = {}
            hidden = focused_workspace(ipc, sway).get('name') == HIDDEN_WORKSPACE
        if state and hidden and action in ('restore', 'restore-or-carousel', 'toggle'):
            if not has_hidden_windows(ipc, sway, state):
                recover_state(ipc, sway, directory)
                state, hidden = {}, False
            elif not (directory / 'capture.ppm').is_file():
                # A lost capture cannot prevent the real windows coming back.
                recover_state(ipc, sway, directory)
                return
        if action == 'restore-or-carousel':
            if state and hidden:
                action = 'restore'
            else:
                clear_state(directory)
                launch_carousel()
                return
        if action == 'toggle':
            action = 'restore' if state and hidden else 'show'
        if action == 'restore':
            if state and hidden:
                try:
                    if animate(ipc, sway, directory, state, restoring=True, session=session):
                        clear_state(directory)
                    else:
                        recover_state(ipc, sway, directory)
                except BaseException:
                    recover_state(ipc, sway, directory)
                    raise
            return
        if hidden or state:
            return
        plan = plan_show(ipc, sway)
        if plan is None:
            return
        try:
            capture(plan['output'], directory / 'capture.ppm')
            write_state(directory, plan)
            if not animate(ipc, sway, directory, plan, restoring=False, session=session):
                recover_state(ipc, sway, directory)
        except BaseException:
            recover_state(ipc, sway, directory)
            raise


def preload_layer_shell():
    """Load gtk4-layer-shell ahead of libwayland-client so it can interpose.

    The library only takes effect when it precedes libwayland-client in the
    global scope; loading it here is the in-process equivalent of LD_PRELOAD.
    """
    import ctypes
    import ctypes.util

    name = ctypes.util.find_library('gtk4-layer-shell') or 'libgtk4-layer-shell.so.0'
    ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)


def animate(ipc, sway, directory, state, restoring, session=None):
    preload_layer_shell()
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gdk', '4.0')
    gi.require_version('Gsk', '4.0')
    gi.require_version('Graphene', '1.0')
    gi.require_version('Gtk4LayerShell', '1.0')
    import cairo
    from gi.repository import GLib, Gdk, Graphene, Gsk, Gtk, Gtk4LayerShell
    Gtk.init()

    data = (directory / 'capture.ppm').read_bytes()
    pixel_width, pixel_height, offset = parse_ppm(data)
    cards = state['cards']
    width, height = float(state['width']), float(state['height'])
    # Each card gets its own texture, cut once.  Sampling the whole capture per
    # card per frame is what drops the slide to a third of the refresh rate.
    scale = pixel_width / width
    textures = []
    for card in cards:
        box = crop_bounds(card, scale, pixel_width, pixel_height)
        pixels = crop_rows(data, offset, pixel_width * 3, box)
        textures.append(Gdk.MemoryTexture.new(box[2], box[3], Gdk.MemoryFormat.R8G8B8,
                                              GLib.Bytes.new(pixels), box[2] * 3))
    del data
    slots = stagger_order(cards)
    vectors = [exit_vector(card, width, height) for card in cards]
    duration = IN_MS if restoring else OUT_MS
    shadow_color = Gdk.RGBA()
    shadow_color.parse(SHADOW_COLOR)

    def draw_card(snapshot, index, travel):
        card = cards[index]
        offset_x, offset_y = vectors[index]
        scale = 1.0 + (SCALE_END - 1.0) * travel
        # Blur tracks speed, not distance: a card is barely moving while it is
        # still full size and most expensive to blur, and fastest once it is
        # small and half off the screen.
        blur = BLUR_END * travel * travel
        card_width, card_height = float(card['width']), float(card['height'])
        snapshot.save()
        snapshot.translate(Graphene.Point().init(
            card['x'] + card_width / 2 + offset_x * travel,
            card['y'] + card_height / 2 + offset_y * travel))
        snapshot.scale(scale, scale)
        snapshot.translate(Graphene.Point().init(-card_width / 2, -card_height / 2))
        bounds = Graphene.Rect().init(0, 0, card_width, card_height)
        outline = Gsk.RoundedRect().init_from_rect(bounds, CORNER_RADIUS)
        # A card at rest sits exactly on the real window and must not double its
        # shadow; the shadow arrives with the movement.  This is the
        # rounded-rectangle shadow, not a blur of the card's own content, which
        # would be recomputed on every frame.
        shading = min(1.0, travel * 8)
        if shading > 0:
            snapshot.push_opacity(shading)
            snapshot.append_outset_shadow(outline, shadow_color, SHADOW_OFFSET[0],
                                          SHADOW_OFFSET[1], 0, SHADOW_RADIUS)
            snapshot.pop()
        if blur > 0:
            snapshot.push_blur(blur)
        snapshot.push_rounded_clip(outline)
        snapshot.append_texture(textures[index], bounds)
        snapshot.pop()
        if blur > 0:
            snapshot.pop()
        snapshot.restore()

    class Stage(Gtk.Widget):
        def __init__(self):
            super().__init__()
            self.travels = [1.0 if restoring else 0.0] * len(cards)
            self.painted = 0

        def do_snapshot(self, snapshot):
            self.painted += 1
            for index in range(len(cards)):
                draw_card(snapshot, index, self.travels[index])

    window = Gtk.Window()
    window.set_decorated(False)
    Gtk4LayerShell.init_for_window(window)
    if not Gtk4LayerShell.is_layer_window(window):
        # Without the overlay there is nothing to hide the swap behind, so the
        # workspace stays exactly where it is.
        window.destroy()
        raise RuntimeError('layer-shell overlay unavailable')
    Gtk4LayerShell.set_namespace(window, 'mbp-intel-showdesktop')
    Gtk4LayerShell.set_layer(window, Gtk4LayerShell.Layer.OVERLAY)
    Gtk4LayerShell.set_keyboard_mode(window, Gtk4LayerShell.KeyboardMode.NONE)
    Gtk4LayerShell.set_exclusive_zone(window, -1)
    for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM,
                 Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
        Gtk4LayerShell.set_anchor(window, edge, True)
    for monitor in Gdk.Display.get_default().get_monitors():
        if monitor.get_connector() == state['output']:
            Gtk4LayerShell.set_monitor(window, monitor)
            break

    # The provider belongs to the display, not to one overlay, so the long-lived
    # helper installs it once instead of stacking a copy on every gesture.
    if not STYLE_INSTALLED:
        provider = Gtk.CssProvider()
        provider.load_from_string('window, window > * { background: none; }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        STYLE_INSTALLED.append(provider)
    stage = Stage()
    window.set_child(stage)

    loop = GLib.MainLoop()
    total = sequence_ms(len(cards), duration)
    schedule = {'phase': 'settle', 'ticks': 0, 'start': 0, 'frame': None,
                'deadline': 0.0, 'completed': False, 'error': None}
    if session:
        session.cancel = loop.quit

    def swap(text, target):
        try:
            current = focused_workspace(ipc, sway)
            expected = (current.get('name') == HIDDEN_WORKSPACE if restoring
                        else current.get('id') == state.get('workspace_id', current.get('id')))
            if not expected:
                if session:
                    session.focused(current)
                loop.quit()
                return False
            if session:
                return session.swap(text, target)
            ipc['command'](sway, text)
            return True
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            schedule['error'] = error
            loop.quit()
            return False

    def tick(widget, clock):
        if session and session.cancelled:
            loop.quit()
            return GLib.SOURCE_CONTINUE
        now = clock.get_frame_time() / 1000.0
        phase = schedule['phase']
        if phase == 'settle':
            # The overlay has to be on the screen before the workspace moves
            # underneath it, or the swap shows through as a flash of bare
            # desktop.  A tick does not prove a frame was presented, so this
            # waits for the compositor's presentation feedback for the frame
            # that carried the first snapshot, and gives up after a deadline
            # rather than stalling if that feedback never arrives.
            stage.queue_draw()
            if stage.painted < 1:
                schedule['deadline'] = now + PRESENT_TIMEOUT_MS
                return GLib.SOURCE_CONTINUE
            if schedule['frame'] is None:
                schedule['frame'] = clock.get_frame_counter()
                return GLib.SOURCE_CONTINUE
            timings = clock.get_timings(schedule['frame'])
            presented = timings is not None and timings.get_presentation_time() > 0
            if not presented and now < schedule['deadline']:
                return GLib.SOURCE_CONTINUE
            if not restoring:
                if not swap('workspace ' + json.dumps(HIDDEN_WORKSPACE), {'name': HIDDEN_WORKSPACE}):
                    return GLib.SOURCE_CONTINUE
                state['hidden'] = True
                write_state(directory, state)
                schedule['phase'], schedule['ticks'] = 'hold', 0
            else:
                schedule['phase'], schedule['start'] = 'fly', now
            return GLib.SOURCE_CONTINUE
        if phase == 'hold':
            stage.queue_draw()
            schedule['ticks'] += 1
            if schedule['ticks'] >= 3:
                schedule['phase'], schedule['start'] = 'fly', now
            return GLib.SOURCE_CONTINUE
        if phase == 'fly':
            elapsed = now - schedule['start']
            for index in range(len(cards)):
                stage.travels[index] = travel_at(slots[index], len(cards), elapsed,
                                                 duration, restoring)
            stage.queue_draw()
            if elapsed >= total:
                if restoring:
                    origin = origin_workspace(ipc['request'](sway, 1), state)
                    if origin is None:
                        loop.quit()
                        return GLib.SOURCE_CONTINUE
                    if not swap(exact_switch(origin), {'id': origin['id']}):
                        return GLib.SOURCE_CONTINUE
                    schedule['phase'], schedule['ticks'] = 'land', 0
                else:
                    schedule['completed'] = True
                    loop.quit()
            return GLib.SOURCE_CONTINUE
        stage.queue_draw()
        schedule['ticks'] += 1
        # The cards are at rest and opaque over every window; give the restored
        # workspace a few frames to be composited before uncovering it.
        if schedule['ticks'] >= 4:
            schedule['completed'] = True
            loop.quit()
        return GLib.SOURCE_CONTINUE

    def realized(_widget):
        surface = window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())
        # Uploading a card to the GPU and compiling the blur and shadow shaders
        # both happen the first time a card is actually drawn, which otherwise
        # lands on the first frame of movement and costs it a tenth of a second.
        # Rendering the real thing once offscreen pays for both up front.
        renderer = window.get_renderer()
        if renderer is None:
            return
        viewport = Graphene.Rect().init(0, 0, width, height)
        primer = Gtk.Snapshot()
        for index in range(len(cards)):
            draw_card(primer, index, 0.5)
        node = primer.to_node()
        if node is not None:
            renderer.render_texture(node, viewport)

    window.connect('realize', realized)
    ticker = stage.add_tick_callback(tick)
    window.present()
    watchdog = GLib.timeout_add(3000, loop.quit)
    try:
        loop.run()
    finally:
        # Each closure owns screen pixels: cancellation must release the same
        # resources as a completed animation, including the nested frame loop.
        source = GLib.MainContext.default().find_source_by_id(watchdog)
        if source:
            source.destroy()
        stage.remove_tick_callback(ticker)
        window.set_child(None)
        window.destroy()
        textures.clear()
        if session:
            session.cancel = None
        gc.collect()
    if schedule['error']:
        raise schedule['error']
    return schedule['completed']


def main(action):
    os.umask(0o077)
    try:
        daemon() if action == 'daemon' else run(action)
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(f'mbp-intel-showdesktop: {error}')
