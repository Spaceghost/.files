"""Select workspace applications and retain user-controlled workspace names."""
import unicodedata

THEMES = {'0': 'STRATA', '1': 'GHOST', '2': 'ORBIT', '3': 'LAB', '4': 'SIGNAL', '5': 'LOUNGE'}


def children(node):
    return node.get('nodes', []) + node.get('floating_nodes', [])


def workspace_nodes(node):
    if node.get('name') in ('__i3', '__i3_scratch'):
        return []
    if node.get('type') == 'workspace':
        return [node]
    return [workspace for child in children(node) for workspace in workspace_nodes(child)]


def is_view(node):
    return bool(node.get('app_id') or node.get('window'))


def all_views(node):
    if is_view(node):
        return [node]
    return [view for child in children(node) for view in all_views(child)]


def displayed_views(node):
    if is_view(node):
        return [node]
    tiled = node.get('nodes', [])
    if node.get('layout') in ('tabbed', 'stacked') and tiled:
        order = node.get('focus', [])
        selected = next((child for identifier in order for child in tiled
                         if child['id'] == identifier), tiled[0])
        tiled = [selected]
    return [view for child in tiled + node.get('floating_nodes', [])
            for view in displayed_views(child)]


def fullscreen_nodes(node):
    if node.get('type') != 'workspace' and node.get('fullscreen_mode', 0):
        return [node]
    return [found for child in children(node) for found in fullscreen_nodes(child)]


def preferred_view(node):
    if is_view(node):
        return node['id']
    available = children(node)
    for identifier in node.get('focus', []):
        for child in available:
            if child['id'] == identifier:
                return preferred_view(child)
    return next((view['id'] for view in all_views(node) if view.get('focused')), None)


def area(view, workspace):
    rect = view.get('rect', {})
    content = view.get('window_rect', {})
    if content.get('width', 0) > 0 and content.get('height', 0) > 0:
        rect = {'x': rect.get('x', 0) + content.get('x', 0),
                'y': rect.get('y', 0) + content.get('y', 0),
                'width': content['width'], 'height': content['height']}
    bounds = workspace.get('rect', rect)
    width = max(0, min(rect.get('x', 0) + rect.get('width', 0),
                       bounds.get('x', 0) + bounds.get('width', 0))
                - max(rect.get('x', 0), bounds.get('x', 0)))
    height = max(0, min(rect.get('y', 0) + rect.get('height', 0),
                        bounds.get('y', 0) + bounds.get('height', 0))
                 - max(rect.get('y', 0), bounds.get('y', 0)))
    return width * height


def largest_view(workspace):
    fullscreen = fullscreen_nodes(workspace)
    candidates = ([view for node in fullscreen for view in displayed_views(node)]
                  if fullscreen else displayed_views(workspace))
    candidates = [view for view in candidates if area(view, workspace) > 0]
    preferred = preferred_view(workspace)
    return max(candidates, key=lambda view: (area(view, workspace),
                                            view['id'] == preferred, -view['id']), default=None)


def safe_label(value, limit=64):
    # Derived names are also consumed by Waybar's workspace click command.
    # Keep them plain and free of Sway/Pango control syntax.
    text = ''.join(' ' if unicodedata.category(char).startswith('C')
                   or char in '\\";$`<>,&' else char for char in str(value))
    return ' '.join(text.split())[:limit].strip()


def addressable_name(value):
    """Return whether Sway's runtime command parser preserves this name exactly."""
    return (isinstance(value, str)
            and not any(unicodedata.category(char).startswith('C')
                        or char in '\\"$' for char in value))


def valid_record(record):
    return (isinstance(record, dict)
            and all(isinstance(record.get(key), str)
                    for key in ('original', 'base', 'rendered')))


def generated_base(value):
    # These named desktop prefixes belong to the service. App suffixes must
    # never become their base when a rename outlives its saved state.
    for number, title in THEMES.items():
        base = f'{number}: {title}'
        if value.startswith(base + ' · '):
            return base
    return value


class WorkspaceNames:
    def __init__(self, records=None):
        self.records = records or {}

    def plan(self, workspace, app):
        identifier = str(workspace['id'])
        current = workspace['name']
        previous = self.records.get(identifier, {})
        if valid_record(previous) and current == previous['rendered']:
            original, base = previous['original'], previous['base']
        else:
            original = current
            base = f'{current}: {THEMES[current]}' if current in THEMES else safe_label(current)
        if not addressable_name(current) or not addressable_name(original):
            return {'id': workspace['id'], 'old': current, 'new': current,
                    'original': original, 'base': base}
        original, base = generated_base(original), generated_base(base)
        label = safe_label(app.get('name', ''), 28) if app else ''
        if label and app.get('kind') in ('codex', 'chatgpt', 'claude'):
            label = '✦ ' + label
        if label and app.get('event') == 'turn-complete':
            label += ' ✓'
        elif label and app.get('event') == 'approval-requested':
            label += ' !'
        separator = ': ' if base.isdigit() else ' · '
        rendered = base + separator + label if label else base
        return {'id': workspace['id'], 'old': current, 'new': rendered,
                'original': original, 'base': base}

    def accept(self, plan):
        self.records[str(plan['id'])] = {'original': plan['original'],
                                       'base': plan['base'], 'rendered': plan['new']}
