"""Window identities, focus history and frozen carousel gestures, without GTK."""

from workspace_model import children, is_view


HELPER_APP_IDS = frozenset((
    'mbp-intel-carousel', 'mbp-intel-agent-switcher', 'mbp-intel-showdesktop',
    'mbp-intel-shortcuts', 'mbp-intel-decoration', 'mbp-intel-expo',
))


def identity(candidate):
    """A reused container number must not inherit a previous window's identity."""
    return tuple(candidate.get(key) for key in ('id', 'pid', 'app_id'))


def _focus_order(node):
    available = children(node)
    by_id = {child.get('id'): child for child in available}
    seen = set()
    for identifier in node.get('focus', []):
        if identifier in by_id and identifier not in seen:
            seen.add(identifier)
            yield by_id[identifier]
    for child in available:
        if child.get('id') not in seen:
            seen.add(child.get('id'))
            yield child


def window_candidates(tree):
    """List normal windows in tree-focus order, used only as the MRU seed.

    Titles remain plain, unmodified text. No process scan or external command
    lies on this path, and hidden windows remain eligible for switching.
    """
    result = []
    seen = set()

    def visit(node, workspace=None, output=None):
        if node.get('name') in ('__i3', '__i3_scratch'):
            return
        if node.get('type') == 'output':
            output = node.get('name')
        elif node.get('type') == 'workspace':
            workspace = node
        if is_view(node):
            identifier = node.get('id')
            if (workspace is None or type(identifier) is not int
                    or identifier in seen or node.get('app_id') in HELPER_APP_IDS):
                return
            seen.add(identifier)
            properties = node.get('window_properties') or {}
            application = (node.get('app_id') or properties.get('class')
                           or properties.get('instance') or 'Window')
            result.append({
                'id': identifier, 'pid': node.get('pid'), 'app_id': node.get('app_id'),
                'title': node.get('name') or application, 'application': application,
                'workspace': workspace.get('name', ''),
                'workspace_id': workspace.get('id'), 'workspace_num': workspace.get('num', -1),
                'output': workspace.get('output') or output,
                'rect': dict(node.get('rect') or {}),
                'focused': bool(node.get('focused')), 'visible': bool(node.get('visible')),
                'foreign_toplevel_identifier': node.get('foreign_toplevel_identifier'),
            })
            return
        for child in _focus_order(node):
            visit(child, workspace, output)

    visit(tree)
    return result


class FocusHistory:
    """Retain global window focus order across workspace and output changes."""

    def __init__(self):
        self._tokens = []

    def update(self, candidates, focused_id=None):
        """Reconcile live windows, then record an explicit or tree-observed focus.

        Existing identities keep their history regardless of tree order. New
        identities follow them in fallback order until a real focus is seen.
        """
        live = {identity(item): item for item in candidates}
        self._tokens = [token for token in self._tokens if token in live]
        known = set(self._tokens)
        self._tokens.extend(token for token in live if token not in known)
        focused = next((item for item in candidates
                        if (item['id'] == focused_id if focused_id is not None
                            else item.get('focused'))), None)
        if focused is not None:
            token = identity(focused)
            self._tokens.remove(token)
            self._tokens.insert(0, token)
        return [dict(live[token]) for token in self._tokens]

    def record(self, candidates, focused_id):
        """Record a Sway window-focus event against the current live identities."""
        return self.update(candidates, focused_id)


class SwitchState:
    """Freeze candidates for one gesture; changes only remove vanished windows."""

    def __init__(self, candidates, action='show'):
        if action not in ('show', 'next', 'previous'):
            raise ValueError('action must be show, next, or previous')
        self.candidates = [dict(item) for item in candidates]
        self.index = None
        if not self.candidates:
            return
        focused = next((index for index, item in enumerate(self.candidates)
                        if item.get('focused')), None)
        if focused is None:
            self.index = len(self.candidates) - 1 if action == 'previous' else 0
        else:
            delta = {'show': 0, 'next': 1, 'previous': -1}[action]
            self.index = (focused + delta) % len(self.candidates)

    @property
    def selected(self):
        if self.index is not None and 0 <= self.index < len(self.candidates):
            return self.candidates[self.index]
        return None

    def step(self, direction):
        if direction not in ('next', 'previous'):
            raise ValueError('direction must be next or previous')
        if self.index is not None:
            delta = 1 if direction == 'next' else -1
            self.index = (self.index + delta) % len(self.candidates)

    def refresh(self, live_candidates):
        """Keep the highlight, or advance to the next surviving frozen identity."""
        live = {identity(item): item for item in live_candidates}
        old_tokens = [identity(item) for item in self.candidates]
        selected = identity(self.selected) if self.selected is not None else None
        if selected not in live and self.index is not None:
            following = old_tokens[self.index + 1:] + old_tokens[:self.index]
            selected = next((token for token in following if token in live), None)
        surviving = [token for token in old_tokens if token in live]
        self.candidates = [dict(live[token]) for token in surviving]
        self.index = surviving.index(selected) if selected in surviving else None
        return self.selected

    def commit_target(self, live_candidates):
        if self.selected is None:
            return None
        live = {identity(item) for item in live_candidates}
        return self.selected['id'] if identity(self.selected) in live else None


def tab_direction(key_name, modifiers):
    if key_name not in ('Tab', 'ISO_Left_Tab'):
        return None
    return 'previous' if key_name == 'ISO_Left_Tab' or 'Shift' in modifiers else 'next'


def modifier_release_commits(family, key_name, modifiers):
    """Use the current aggregate state after release, including both side keys.

    A persistent gesture has no initiating modifier and accepts only explicit
    Enter/click actions. Releasing a different modifier never accepts a choice.
    """
    families = {
        'alt': (('Alt_L', 'Alt_R'), {'Mod1', 'Alt'}),
        'super': (('Super_L', 'Super_R'), {'Mod4', 'Super'}),
    }
    keys, masks = families.get(family, ((), set()))
    return key_name in keys and not masks.intersection(modifiers)


def key_action(key_name, modifiers):
    if key_name == 'Escape':
        return 'cancel'
    if key_name in ('Return', 'KP_Enter'):
        return 'commit'
    return tab_direction(key_name, modifiers)
