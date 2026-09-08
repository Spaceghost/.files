"""Choose attached or workspace captions from one immutable Sway tree snapshot."""
from decoration import focused_child


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
        child = focused_child(node)
        floating = floating or any(child is candidate
                                   for candidate in node.get('floating_nodes', []))
        node = child
    return None, False


def fullscreen_containers(nodes, mode=None):
    """Container flags identify the fullscreen view and its corner policy."""
    return [(node, floating) for node, floating in nodes
            if node.get('type') not in ('root', 'output', 'workspace')
            and node.get('fullscreen_mode')
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
