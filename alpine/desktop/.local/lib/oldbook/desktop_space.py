"""Shared logical screen space for desktop cards, Scripture search and effects.

Two readings of one question live here. `screen_space` answers it as four
margins, which is what a reading card needs to be placed. `free_region` answers
it as a region, which is what a surface drawing between the windows needs, and
it is deliberately the same reading: the same surface list, the same skips, the
same output-local extents.
"""
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import socket

from decoration import focused_child
from decoration_placement import descendants, fullscreen_containers
from decoration_watch import _send, _receive

EDGE_MARGIN = 16
CAPTION_CLEARANCE = 60
SEARCH_WIDTH = 760
SEARCH_HEIGHT = 64
# The window decoration's own surfaces: the caption strip -- docked in its band
# or attached to a window, on the bottom or the right -- and the band itself.
DECORATION = ('oldbook-decoration', 'oldbook-decoration-band')
# The Scripture bar's one setting, under XDG_CONFIG_HOME.
SEARCH_SETTINGS = Path('oldbook/scripture-bar.json')
SEARCH_CLEARANCE_LIMIT = 400

# The free region is published on the grid `oldbook-conky` already analyses the
# painting with, so "is this cell free" and "is the painting calm here" are one
# lookup in one coordinate system rather than two that nearly agree.
GRID_COLUMNS, GRID_ROWS = 72, 45

# The only surfaces a BOTTOM-layer effect is entitled to cover. It sits one
# layer above the whole background layer, so everything else down there is
# painted over -- and that includes `conky`, which is one surface per reading
# card. Leaving Conky out of the occupied set is the way this goes wrong.
COVERABLE = frozenset({'wallpaper', 'oldbook-background', 'oldbook-decoration-band'})
EFFECT_NAMESPACE = 'oldbook-edges'
# The landing wave. It is an OVERLAY surface over the lower third of the
# output for under a second, anchored to the bottom edge and as wide as the
# screen, which is exactly the shape of a fixed bottom bar -- and it is
# nothing of the kind: it refracts a photograph of what is under it and takes
# no input. Reserving it lifted the Scripture search bar a third of the way up
# the screen on the next one-second poll and dropped it back on the one after,
# every time the strip landed. Jack: "The ripple.py should be ignored by the
# conky bible bar."
RIPPLE_NAMESPACE = 'oldbook-ripple'


def screen_space(output, tree, decoration=True):
    """Reserve occupied edges, excluding floating captions and our own cards.

    SwayFX surface extents are output-local; tree rectangles are global.
    Workspace fullscreen markers are synthetic and must never reserve space.
    With `decoration=False` the window decoration is not read at all, on any
    layer or edge: that is the Scripture bar's reading, because a bar that
    followed the caption strip jumped every time the strip docked or attached.
    """
    rect = output['rect']
    width, height = int(rect['width']), int(rect['height'])
    space = {'name': output['name'], 'width': width, 'height': height,
             'top': CAPTION_CLEARANCE, 'bottom': EDGE_MARGIN,
             'left': EDGE_MARGIN, 'right': EDGE_MARGIN, 'origin_y': 0}
    for surface in output.get('layer_shell_surfaces', []):
        name, layer = surface.get('namespace') or '', surface.get('layer')
        # swaync popups and its control center are transient overlays; the popup
        # window spans the full free height, so it would read as a right strip.
        # The backdrop is skipped by name rather than by luck: a full-output
        # surface at the origin happens to match none of the three edge tests
        # below today, and CONKY-READING forbids the reflow that would follow if
        # it ever did.
        if (layer == 'background'
                or name in ('conky', 'wallpaper', 'oldbook-scripture', EFFECT_NAMESPACE,
                            RIPPLE_NAMESPACE)
                or name.startswith('swaync')
                or (name == 'oldbook-decoration' and layer == 'top')
                or (not decoration and name in DECORATION)):
            continue
        extent = surface.get('extent', {})
        x, y = extent.get('x', 0), extent.get('y', 0)
        w, h = extent.get('width', 0), extent.get('height', 0)
        if w <= 0 or h <= 0:
            continue
        if name == 'top' and y < height / 2:
            space['origin_y'] = max(space['origin_y'], y + h)
            space['top'] = max(space['top'], y + h + EDGE_MARGIN)
        if w >= h and y >= height / 2 and y + h > height - CAPTION_CLEARANCE:
            space['bottom'] = max(space['bottom'], CAPTION_CLEARANCE,
                                  height - y + EDGE_MARGIN)
        if h > w and x >= width / 2 and x + w > width - CAPTION_CLEARANCE:
            space['right'] = max(space['right'], CAPTION_CLEARANCE,
                                 width - x + EDGE_MARGIN)
    global_views = fullscreen_containers(list(descendants(tree)), mode=2)
    node = next((node for node in tree.get('nodes', [])
                 if node.get('name') == output['name']), {})
    workspace = focused_child(node) or {}
    visible = list(descendants(workspace))
    if global_views or fullscreen_containers(visible):
        space['bottom'] = max(space['bottom'], CAPTION_CLEARANCE)
    for window, floating in visible:
        if floating or not (window.get('app_id') or window.get('window')):
            continue
        bounds = window.get('rect', {})
        if (bounds.get('y', 0) + bounds.get('height', 0)
                > rect.get('y', 0) + height - CAPTION_CLEARANCE):
            space['bottom'] = max(space['bottom'], CAPTION_CLEARANCE)
    return space


def search_clearance(path=None):
    """How far above the output's bottom edge the Scripture bar sits.

    The default clears the bottom bars area outright -- the caption band and the
    strip docked in it -- without reading where either is, so the bar starts out
    of their way and never has to move. `bottom_clearance` in
    ~/.config/oldbook/scripture-bar.json changes it; a missing, unreadable or
    unreasonable file keeps the default.
    """
    if path is None:
        base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
        path = Path(base) / SEARCH_SETTINGS
    try:
        value = json.loads(Path(path).read_text()).get('bottom_clearance', CAPTION_CLEARANCE)
    except (OSError, ValueError, AttributeError):
        return CAPTION_CLEARANCE
    if (isinstance(value, bool) or not isinstance(value, int)
            or not 0 <= value <= SEARCH_CLEARANCE_LIMIT):
        return CAPTION_CLEARANCE
    return value


def search_bottom(screen, clearance=None):
    """The bar's distance from the bottom edge: its clearance, or a real bar's depth."""
    clearance = search_clearance() if clearance is None else clearance
    return max(clearance, screen.get('bottom', EDGE_MARGIN))


def search_rectangle(screen, clearance=None):
    left, right = screen.get('left', EDGE_MARGIN), screen.get('right', EDGE_MARGIN)
    width = min(SEARCH_WIDTH, max(1, screen['width'] - left - right))
    # Center inside the free horizontal span when a fixed right strip is present.
    return {'x': left + max(0, (screen['width'] - left - right - width) // 2),
            'y': max(0, screen['height'] - search_bottom(screen, clearance) - SEARCH_HEIGHT),
            'width': width, 'height': SEARCH_HEIGHT}


def conky_space(screen):
    """Keep cards in clearance positions so window changes need no reflow."""
    return dict(screen, bottom=max(CAPTION_CLEARANCE, screen['bottom']),
                right=max(CAPTION_CLEARANCE, screen['right']))


def request(connection, kind):
    """One Sway IPC request on an open connection, checked against its reply."""
    _send(connection, kind)
    replied, body = _receive(connection)
    if replied != kind:
        raise ValueError(f'Unexpected Sway IPC response: {replied}')
    return json.loads(body)


def read_layout(socket_path=None, connection=None):
    """Active outputs and the tree, from one connection rather than swaymsg.

    An open connection is reused when the caller has one, which is what the
    space service does: the same two requests every wake, on the socket it
    already holds.
    """
    if connection is not None:
        outputs, tree = request(connection, 3), request(connection, 4)
    else:
        # Two small IPC requests on one connection avoid repeatedly spawning swaymsg.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as opened:
            opened.settimeout(.25)
            opened.connect(socket_path or os.environ.get('SWAYSOCK', ''))
            outputs, tree = request(opened, 3), request(opened, 4)
    return [output for output in outputs if output.get('active')], tree


def read_screen(socket_path=None, output_name=None, decoration=True):
    outputs, tree = read_layout(socket_path)
    if not outputs:
        raise RuntimeError('No active output to place desktop panels on')
    physical = [output for output in outputs if not output['name'].startswith(('HEADLESS', 'WL-'))]
    candidates = physical or outputs
    chosen = next((output for output in outputs if output['name'] == output_name), None)
    chosen = chosen or next((output for output in candidates if output.get('focused')), candidates[0])
    return screen_space(chosen, tree, decoration)


def surface_rectangles(output, namespace=EFFECT_NAMESPACE):
    """Layer surfaces a BOTTOM-layer effect must stay out of, output-local.

    Everything the compositor reports is an occupier unless it is in `COVERABLE`
    or is the effect itself. That is how Conky survives: each reading card is a
    `conky` surface with its own extent and nothing here skips it. swaync is the
    one exception, and for the reason `screen_space` already skips it -- it keeps
    an output-tall host mapped whether or not a notification is showing, and
    NOTIFICATION-PLACEMENT keeps that host transparent, so reserving it would
    carve a permanent empty strip out of the region.
    """
    rectangles = []
    for surface in output.get('layer_shell_surfaces', []):
        name = surface.get('namespace') or ''
        # The ripple is skipped for the opposite reason to swaync: it is not
        # transparent but it is a picture of exactly what it covers, taken a
        # moment before, so whatever draws under it is what it shows. Carving
        # its band out of the region would have the effect clear a third of
        # the output for the length of a wave and then come back.
        if (name in COVERABLE or name == namespace or name.startswith('swaync')
                or name == RIPPLE_NAMESPACE):
            continue
        extent = surface.get('extent') or {}
        width, height = int(extent.get('width', 0)), int(extent.get('height', 0))
        if width <= 0 or height <= 0:
            continue
        rectangles.append({'x': int(extent.get('x', 0)), 'y': int(extent.get('y', 0)),
                           'width': width, 'height': height, 'kind': 'layer', 'name': name})
    return rectangles


def window_rectangles(output, tree):
    """Windows on this output's visible workspace, output-local, and fullscreen.

    Tiled and floating alike: a BOTTOM surface is under both and must clip to
    neither more nor less than what they cover. A fullscreen view is reported as
    a state rather than as a rectangle, because it covers the whole output and
    the answer for a consumer is to stop drawing rather than to clip.

    Container `rect` is the outer geometry including sway's own decoration,
    which is the rectangle a surface underneath actually loses.
    """
    rect = output['rect']
    origin_x, origin_y = int(rect.get('x', 0)), int(rect.get('y', 0))
    node = next((item for item in tree.get('nodes', [])
                 if item.get('name') == output['name']), {})
    workspace = next((child for child in node.get('nodes', [])
                      if child.get('name') == node.get('current_workspace')), None)
    workspace = workspace if workspace is not None else (focused_child(node) or {})
    visible = list(descendants(workspace))
    # A workspace carries a synthetic fullscreen marker; only a view counts.
    fullscreen = bool(fullscreen_containers(visible)
                      or fullscreen_containers(list(descendants(tree)), mode=2))
    rectangles = []
    for window, _floating in visible:
        if not (window.get('app_id') or window.get('window')):
            continue
        if window.get('fullscreen_mode'):
            continue
        bounds = window.get('rect') or {}
        width, height = int(bounds.get('width', 0)), int(bounds.get('height', 0))
        if width <= 0 or height <= 0:
            continue
        rectangles.append({'x': int(bounds.get('x', 0)) - origin_x,
                           'y': int(bounds.get('y', 0)) - origin_y,
                           'width': width, 'height': height, 'kind': 'window',
                           'name': window.get('app_id') or 'xwayland'})
    return rectangles, fullscreen


def occupancy_grid(width, height, rectangles, columns=GRID_COLUMNS, rows=GRID_ROWS):
    """One string per grid row: '.' free, '#' covered by anything at all.

    A cell that a rectangle touches at all is taken. Rounding the other way
    would let an effect paint into the last few pixels of a reading card, and
    half a card is a card.
    """
    grid = [bytearray(b'.' * columns) for _ in range(rows)]
    if width > 0 and height > 0:
        for rectangle in rectangles:
            left = min(columns, max(0, math.floor(rectangle['x'] * columns / width)))
            right = min(columns, max(0, math.ceil(
                (rectangle['x'] + rectangle['width']) * columns / width)))
            top = min(rows, max(0, math.floor(rectangle['y'] * rows / height)))
            bottom = min(rows, max(0, math.ceil(
                (rectangle['y'] + rectangle['height']) * rows / height)))
            for row in range(top, bottom):
                grid[row][left:right] = b'#' * max(0, right - left)
    return [bytes(row).decode() for row in grid]


def free_region(output, tree, namespace=EFFECT_NAMESPACE):
    """Where a BOTTOM-layer surface on this output may draw, as rects and grid."""
    rect = output['rect']
    width, height = int(rect['width']), int(rect['height'])
    windows, fullscreen = window_rectangles(output, tree)
    occupied = surface_rectangles(output, namespace) + windows
    grid = occupancy_grid(width, height, occupied)
    return {'output': output['name'],
            'rect': {'x': int(rect.get('x', 0)), 'y': int(rect.get('y', 0)),
                     'width': width, 'height': height},
            'scale': output.get('scale', 1),
            'columns': GRID_COLUMNS, 'rows': GRID_ROWS,
            'fullscreen': fullscreen, 'occupied': occupied, 'grid': grid,
            'free_cells': sum(row.count('.') for row in grid)}


def describe(socket_path=None, connection=None, namespace=EFFECT_NAMESPACE):
    """The free region of every active output, read once from the compositor."""
    outputs, tree = read_layout(socket_path, connection)
    return {'version': 1, 'namespace': namespace,
            'regions': [free_region(output, tree, namespace) for output in outputs]}


def session_key():
    identity = os.environ.get('SWAYSOCK') or os.environ.get('WAYLAND_DISPLAY') or 'default'
    return hashlib.sha256(identity.encode()).hexdigest()[:12]


def runtime_directory(runtime=None):
    runtime = runtime or os.environ.get('XDG_RUNTIME_DIR')
    if not runtime:
        raise RuntimeError('XDG_RUNTIME_DIR is required to publish the free region')
    directory = Path(runtime) / 'oldbook'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def state_path(runtime=None):
    return runtime_directory(runtime) / 'space.json'


def lock_path(runtime=None):
    return runtime_directory(runtime) / f'space-{session_key()}.lock'


def publish(record, runtime=None):
    path = state_path(runtime)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)


def retract(runtime=None):
    """Leave nothing behind: with no consumer there is no record to read."""
    try:
        state_path(runtime).unlink(missing_ok=True)
    except (OSError, RuntimeError):
        pass


def published(runtime=None, socket_path=None):
    """The running service's record, or a fresh reading when it is not running.

    A consumer never has to care whether the service is up, exactly as with the
    power posture: with no service it pays one round trip and gets a true
    answer, only without the change notifications.
    """
    try:
        return json.loads(state_path(runtime).read_text())
    except (OSError, ValueError, RuntimeError):
        return describe(socket_path)


def subscriber_directory(runtime=None, create=False):
    directory = runtime_directory(runtime) / 'space.d'
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def subscribers(runtime=None):
    """Names of consumers still holding their claim; stale claims are swept.

    A claim is a file its owner holds an exclusive flock on for its whole life,
    so a consumer that crashed releases it with no cleanup of its own and the
    service stops on its own shortly after.
    """
    live = []
    try:
        directory = subscriber_directory(runtime)
        if not directory.is_dir():
            # Asking who is subscribed must not itself leave anything behind.
            return live
        entries = sorted(directory.iterdir())
    except (OSError, RuntimeError):
        return live
    for path in entries:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open('a') as claim:
                try:
                    fcntl.flock(claim, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    live.append(path.name)
                    continue
            path.unlink(missing_ok=True)
        except OSError:
            continue
    return live


class Subscription:
    """A consumer's claim on the free region, held for as long as it draws."""

    def __init__(self, name, runtime=None):
        if not name or '/' in name or name.startswith('.'):
            raise ValueError(f'Unsafe space subscriber name: {name}')
        self.path = subscriber_directory(runtime, create=True) / f'{name}.{os.getpid()}'
        self.claim = None

    def __enter__(self):
        self.claim = self.path.open('a')
        try:
            fcntl.flock(self.claim, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.claim.close()
            self.claim = None
            raise RuntimeError(f'Space subscription already held: {self.path}')
        return self

    def __exit__(self, *_):
        if self.claim is not None:
            self.claim.close()
            self.claim = None
        self.path.unlink(missing_ok=True)
        return False
