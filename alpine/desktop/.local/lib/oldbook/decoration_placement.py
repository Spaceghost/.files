"""Choose attached or workspace captions from one immutable Sway tree snapshot."""
from decoration import IGNORED_CAPTION_APPS, caption_child, focused_child
from decoration_reserve import band_clearance


def descendants(node, floating=False):
    """Walk every branch, retaining whether a container belongs to a float."""
    floating = floating or node.get('type') == 'floating_con'
    yield node, floating
    for child in node.get('nodes', []):
        yield from descendants(child, floating)
    for child in node.get('floating_nodes', []):
        yield from descendants(child, True)


def focused_window(workspace):
    node = workspace
    floating = False
    while node:
        floating = floating or node.get('type') == 'floating_con'
        if node.get('app_id') or node.get('window'):
            return node, floating
        child = caption_child(node)
        floating = floating or any(child is candidate
                                   for candidate in node.get('floating_nodes', []))
        node = child
    return None, False


def fullscreen_containers(nodes, mode=None):
    """Container flags identify the fullscreen view and its corner policy."""
    return [(node, floating) for node, floating in nodes
            if node.get('type') not in ('root', 'output', 'workspace')
            and node.get('fullscreen_mode')
            # A console or a wrapper containing only consoles has no caption.
            and node.get('app_id') not in IGNORED_CAPTION_APPS
            and (node.get('app_id') or node.get('window') or caption_child(node) is not None)
            and (mode is None or node['fullscreen_mode'] == mode)]


def rectangle(node):
    source = node.get('rect', {})
    return {key: source.get(key, 0) for key in ('x', 'y', 'width', 'height')}


def output_placements(tree, preferred_edge='bottom'):
    """Return placements for visible workspaces without changing the saved edge.

    A focused floating view owns its caption until any container in its visible
    workspace is fullscreen. Global fullscreen overrides every output. Hidden
    workspaces only participate when their fullscreen mode is global (2).
    Rectangles use Sway's global logical coordinates and are independent copies.
    """
    if preferred_edge not in ('bottom', 'right'):
        raise ValueError('Decoration edge must be bottom or right')
    all_nodes = list(descendants(tree))
    # Sway hardcodes workspace fullscreen_mode=1 even without fullscreen views.
    # Only actual container flags describe fullscreen, including global mode 2.
    global_views = fullscreen_containers(
        [(node, floating) for node, floating in all_nodes if node is not tree], mode=2)
    global_fullscreen = bool(global_views)
    placements = {}
    for output in tree.get('nodes', []):
        name = output.get('name', '')
        if output.get('type') != 'output' or not name or name.startswith('__'):
            continue
        workspace = focused_child(output)
        if workspace is None:
            continue
        window, floating = focused_window(workspace)
        local_nodes = list(descendants(workspace))
        local_views = fullscreen_containers(
            [(node, state) for node, state in local_nodes if node is not workspace])
        fullscreen = global_fullscreen or bool(local_views)
        fullscreen_views = global_views if global_fullscreen else local_views
        square = any(not state for _, state in fullscreen_views)
        attached = bool(window and floating and not fullscreen)
        placements[name] = {
            'mode': 'window' if attached else 'workspace',
            'edge': 'bottom' if fullscreen else preferred_edge,
            'rect': rectangle(window if attached else output),
            'square': square,
            'window_id': window.get('id') if window else None,
        }
    return placements


def band_corrections(tree, regions, edge):
    """Floating windows sitting in the band, and where each one has to go.

    The band's exclusive zone is honoured -- the usable area proves it -- but an
    exclusive zone is a tiling instruction and nothing else. Sway places a new
    float inside the workspace once, and after that the position belongs to
    whoever moves it: `seatop_move_floating` clamps a drag against nothing at
    all, and `arrange_workspace` only re-fixes floating coordinates when the
    workspace origin moves, which a bottom reservation never does. So every
    float that was on screen before the band appeared, and every one dragged
    down since, sits on top of the reservation with nothing to put it back.

    Only visible top-level floats are considered. A fullscreen view is meant to
    cover the band; a scratchpad window belongs to the helper that parks and
    positions it; a tiled window is the compositor's own business.
    """
    corrections = []
    for output in tree.get('nodes', []):
        name = output.get('name', '')
        if output.get('type') != 'output' or not name or name.startswith('__'):
            continue
        region = regions.get(name)
        workspace = focused_child(output)
        if not region or workspace is None:
            continue
        bounds = rectangle(workspace)
        for node in workspace.get('floating_nodes', []):
            identity = node.get('id')
            if identity is None or node.get('fullscreen_mode'):
                continue
            if node.get('scratchpad_state', 'none') != 'none':
                continue
            if not (node.get('app_id') or node.get('window')
                    or caption_child(node) is not None):
                continue
            rect = rectangle(node)
            position = band_clearance(rect, region, edge, bounds)
            if position is not None:
                corrections.append({'id': identity, 'output': name,
                                    'rect': rect, 'position': position})
    return corrections
