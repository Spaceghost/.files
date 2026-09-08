"""Shared logical screen space for desktop cards and Scripture search."""
import json
import os
import socket

from decoration import focused_child
from decoration_placement import descendants, fullscreen_containers
from decoration_watch import _send, _receive

EDGE_MARGIN = 16
CAPTION_CLEARANCE = 60
SEARCH_WIDTH = 760
SEARCH_HEIGHT = 64


def screen_space(output, tree):
    """Reserve occupied edges, excluding floating captions and our own cards.

    SwayFX surface extents are output-local; tree rectangles are global.
    Workspace fullscreen markers are synthetic and must never reserve space.
    """
    rect = output['rect']
    width, height = int(rect['width']), int(rect['height'])
    space = {'name': output['name'], 'width': width, 'height': height,
             'top': CAPTION_CLEARANCE, 'bottom': EDGE_MARGIN,
             'left': EDGE_MARGIN, 'right': EDGE_MARGIN, 'origin_y': 0}
    for surface in output.get('layer_shell_surfaces', []):
        name, layer = surface.get('namespace'), surface.get('layer')
        if (layer == 'background' or name in ('conky', 'wallpaper', 'oldbook-scripture')
                or (name == 'oldbook-decoration' and layer == 'top')):
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


def search_rectangle(screen):
    left, right = screen.get('left', EDGE_MARGIN), screen.get('right', EDGE_MARGIN)
    width = min(SEARCH_WIDTH, max(1, screen['width'] - left - right))
    # Center inside the free horizontal span when a fixed right strip is present.
    return {'x': left + max(0, (screen['width'] - left - right - width) // 2),
            'y': max(0, screen['height'] - screen.get('bottom', EDGE_MARGIN) - SEARCH_HEIGHT),
            'width': width, 'height': SEARCH_HEIGHT}


def conky_space(screen):
    """Keep cards in clearance positions so window changes need no reflow."""
    return dict(screen, bottom=max(CAPTION_CLEARANCE, screen['bottom']),
                right=max(CAPTION_CLEARANCE, screen['right']))


def read_screen(socket_path=None, output_name=None):
    # Two small IPC requests on one connection avoid repeatedly spawning swaymsg.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(.25)
        connection.connect(socket_path or os.environ.get('SWAYSOCK', ''))
        _send(connection, 3)
        kind, body = _receive(connection)
        if kind != 3:
            raise ValueError('Unexpected Sway output response')
        outputs = json.loads(body)
        _send(connection, 4)
        kind, body = _receive(connection)
        if kind != 4:
            raise ValueError('Unexpected Sway tree response')
        tree = json.loads(body)
    outputs = [output for output in outputs if output.get('active')]
    if not outputs:
        raise RuntimeError('No active output to place desktop panels on')
    physical = [output for output in outputs if not output['name'].startswith(('HEADLESS', 'WL-'))]
    candidates = physical or outputs
    chosen = next((output for output in outputs if output['name'] == output_name), None)
    chosen = chosen or next((output for output in candidates if output.get('focused')), candidates[0])
    return screen_space(chosen, tree)
