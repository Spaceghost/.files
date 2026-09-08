"""Transient, agent-only Alt+Tab switcher for the Sway desktop."""
import fcntl
import hashlib
import os
from pathlib import Path
import runpy
import socket
import time

from app_identity import ApplicationResolver
from overlay_theme import gtk_css, read_palette
from workspace_model import all_views, safe_label, workspace_nodes


AGENT_KINDS = frozenset(('codex', 'chatgpt', 'claude'))
AGENT_APP_IDS = frozenset(('mbp-intel-agent', 'mbp-intel-agent-quick'))
COMMANDS = frozenset(('next', 'previous', 'commit', 'cancel'))


def _children_in_focus_order(node):
    children = node.get('nodes', []) + node.get('floating_nodes', [])
    by_id = {child.get('id'): child for child in children}
    ordered = [by_id[identifier] for identifier in node.get('focus', [])
               if identifier in by_id]
    ordered.extend(child for child in children if child not in ordered)
    return ordered


def _views_in_focus_order(node):
    if node.get('app_id') or node.get('window'):
        return [node]
    return [view for child in _children_in_focus_order(node)
            for view in _views_in_focus_order(child)]


def agent_candidates(tree, resolver):
    """Return agent windows in Sway's most-recent-focus traversal order."""
    workspaces = workspace_nodes(tree)
    workspace_by_view = {
        view['id']: workspace
        for workspace in workspaces
        for view in all_views(workspace)
        if type(view.get('id')) is int and not isinstance(view.get('id'), bool)
    }
    views = [view for view in _views_in_focus_order(tree)
             if view.get('id') in workspace_by_view]
    identities = resolver.resolve_all(views)
    candidates = []
    for view in views:
        identity = identities.get(view['id'], {})
        app_id = view.get('app_id')
        if identity.get('kind') not in AGENT_KINDS and app_id not in AGENT_APP_IDS:
            continue
        agent = identity.get('name') if identity.get('kind') in AGENT_KINDS else 'Agent'
        if identity.get('tmux_pane'):
            agent += ' (tmux)'
        title = safe_label(view.get('name') or agent, 72) or agent
        workspace = workspace_by_view[view['id']]
        candidates.append({
            'id': view['id'],
            'workspace': safe_label(workspace.get('name', ''), 48),
            'title': title,
            'agent': safe_label(agent, 40),
            'kind': identity.get('kind') if identity.get('kind') in AGENT_KINDS else 'agent',
            'event': identity.get('event'),
            'focused': bool(view.get('focused')),
            'pid': view.get('pid'),
            'app_id': app_id,
        })
    return candidates


class SwitchState:
    """Frozen candidates and current highlight for one Alt gesture."""

    def __init__(self, candidates, direction):
        self.candidates = list(candidates)
        self.index = None
        if not self.candidates:
            return
        focused = next((index for index, item in enumerate(self.candidates)
                        if item.get('focused')), None)
        if focused is None:
            self.index = 0 if direction == 'next' else len(self.candidates) - 1
        else:
            delta = 1 if direction == 'next' else -1
            self.index = (focused + delta) % len(self.candidates)

    @property
    def selected(self):
        return self.candidates[self.index] if self.index is not None else None

    def step(self, direction):
        if self.index is not None:
            delta = 1 if direction == 'next' else -1
            self.index = (self.index + delta) % len(self.candidates)

    def commit_target(self, fresh_candidates):
        if self.selected is None:
            return None
        token = tuple(self.selected.get(key) for key in ('id', 'pid', 'app_id'))
        live = {tuple(item.get(key) for key in ('id', 'pid', 'app_id'))
                for item in fresh_candidates}
        return self.selected['id'] if token in live else None


def alt_release_commits(key_name, modifiers):
    """Final Alt release commits; releasing one of two held Alts does not."""
    return key_name in ('Alt_L', 'Alt_R') and 'Mod1' not in modifiers


def tab_direction(key_name, modifiers):
    if key_name not in ('Tab', 'ISO_Left_Tab'):
        return None
    return 'previous' if key_name == 'ISO_Left_Tab' or 'Shift' in modifiers else 'next'


def switcher_mode(reply):
    return isinstance(reply, dict) and reply.get('name') == 'agent-switcher'


def revealed_scroll_value(item_top, item_bottom, value, page_size):
    if item_top < value:
        return item_top
    if item_bottom > value + page_size:
        return item_bottom - page_size
    return value


def popup_content_height(candidate_count):
    """Show ordinary agent sets together and scroll unusually large sets."""
    return min(480, max(64, candidate_count * 64))


def _runtime_paths(runtime, sway):
    identity = hashlib.sha256(str(sway).encode()).hexdigest()[:12]
    directory = runtime / 'mbp-intel'
    return (directory / ('agent-switcher-' + identity + '.sock'),
            directory / ('agent-switcher-' + identity + '.lock'))


def _send(address, action):
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.sendto(action.encode(), str(address))


def claim_or_forward(lock, address, action, attempts=20, delay=.01):
    """Own the next server generation, or forward to the current generation."""
    for _attempt in range(attempts):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            try:
                _send(address, action)
                return False
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(delay)
    return False


def _focus(ipc, sway, target):
    ipc['command'](sway, f'[con_id={int(target)}] focus')


class Popup:
    """GTK layer surface that owns ordered Tab and Alt-release events."""

    CSS = '''
    #agent-switcher { background: transparent; }
    #agent-switcher-panel {
        background: alpha(@theme_background, 0.96);
        border: 2px solid @theme_border;
        border-radius: 16px;
        padding: 14px;
    }
    #agent-switcher-heading { color: @theme_accent; font-size: 1.1em; font-weight: bold; }
    .agent-card { background: alpha(@theme_surface, 0.88); border-radius: 10px; padding: 9px 13px; }
    .agent-card.selected { background: alpha(@theme_accent, 0.24); border: 1px solid @theme_accent; }
    .agent-title { color: @theme_foreground; font-weight: bold; }
    .agent-detail { color: @theme_muted; font-size: 0.88em; }
    '''

    def __init__(self, state, on_command, on_map):
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        gi.require_version('GtkLayerShell', '0.1')
        from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

        self.Gdk, self.GLib, self.Gtk = Gdk, GLib, Gtk
        self.state = state
        self.on_command = on_command
        self.on_map = on_map
        self.closed = False
        self.palette = None
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_name('agent-switcher')
        self.window.set_title('Agent window switcher')
        self.window.set_decorated(False)
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, 'mbp-intel-agent-switcher')
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        self.window.connect('key-press-event', self._key_press)
        self.window.connect('key-release-event', self._key_release)
        self.window.connect('destroy', lambda *_args: Gtk.main_quit())
        self.window.connect('map-event', self._mapped)

        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            self.window.get_screen(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.refresh_theme()
        self.theme_timer = GLib.timeout_add_seconds(1, self.refresh_theme)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.set_name('agent-switcher-panel')
        heading = Gtk.Label(label='AGENT WINDOWS')
        heading.set_name('agent-switcher-heading')
        heading.set_xalign(0)
        panel.pack_start(heading, False, False, 0)
        cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.cards = []
        for candidate in state.candidates:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.get_style_context().add_class('agent-card')
            title = Gtk.Label(label=candidate['title'])
            title.set_xalign(0)
            title.set_ellipsize(3)
            title.get_style_context().add_class('agent-title')
            detail = Gtk.Label(label=candidate['workspace'] + '  ·  ' + candidate['agent'])
            detail.set_xalign(0)
            detail.set_ellipsize(3)
            detail.get_style_context().add_class('agent-detail')
            card.pack_start(title, False, False, 0)
            card.pack_start(detail, False, False, 0)
            cards_box.pack_start(card, False, False, 0)
            self.cards.append(card)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_min_content_height(popup_content_height(len(self.cards)))
        scroll.set_max_content_height(480)
        scroll.add(cards_box)
        self.scroll = scroll
        panel.pack_start(scroll, True, True, 0)
        self.window.set_size_request(560, -1)
        self.window.add(panel)
        self.render()

    def render(self):
        for index, card in enumerate(self.cards):
            context = card.get_style_context()
            (context.add_class if index == self.state.index else context.remove_class)('selected')
        self.GLib.idle_add(self._reveal_selected)

    def _reveal_selected(self):
        if self.closed or self.state.index is None:
            return False
        allocation = self.cards[self.state.index].get_allocation()
        adjustment = self.scroll.get_vadjustment()
        value = revealed_scroll_value(
            allocation.y, allocation.y + allocation.height,
            adjustment.get_value(), adjustment.get_page_size())
        adjustment.set_value(value)
        return False

    def refresh_theme(self):
        palette = read_palette()
        if palette != self.palette:
            self.provider.load_from_data(gtk_css(self.CSS, palette))
            self.palette = palette
        return not self.closed

    def _key_press(self, _window, event):
        key_name = self.Gdk.keyval_name(event.keyval)
        if key_name == 'Escape':
            self.on_command('cancel')
            return True
        modifiers = {'Shift'} if event.state & self.Gdk.ModifierType.SHIFT_MASK else set()
        direction = tab_direction(key_name, modifiers)
        if direction is not None:
            self.on_command(direction)
            return True
        return False

    def _key_release(self, _window, event):
        key_name = self.Gdk.keyval_name(event.keyval)
        if key_name in ('Alt_L', 'Alt_R'):
            self.GLib.idle_add(self._commit_if_alt_is_up, key_name)
            return True
        return False

    def _mapped(self, *_args):
        self.on_map()
        # The initiating Alt may have been released before the surface mapped.
        self.GLib.timeout_add(50, self._commit_if_alt_is_up, 'Alt_L')
        return False

    def _commit_if_alt_is_up(self, key_name):
        if self.closed:
            return False
        keymap = self.Gdk.Keymap.get_for_display(self.window.get_display())
        modifiers = ({'Mod1'} if keymap.get_modifier_state()
                     & self.Gdk.ModifierType.MOD1_MASK else set())
        if alt_release_commits(key_name, modifiers):
            self.on_command('commit')
        return False

    def show(self):
        self.window.show_all()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.GLib.source_remove(self.theme_timer)
        self.Gtk.StyleContext.remove_provider_for_screen(
            self.window.get_screen(), self.provider)
        self.window.destroy()


def _run_server(action, ipc, sway, control):
    candidates = agent_candidates(ipc['request'](sway, 4), ApplicationResolver())
    state = SwitchState(candidates, action)
    if state.selected is None:
        return
    running = True
    commit_target = None
    mode_active = False
    popup = None

    def finish(command):
        nonlocal running, commit_target
        if command in ('next', 'previous'):
            state.step(command)
            popup.render()
            return
        if command == 'commit':
            try:
                if switcher_mode(ipc['request'](sway, 12)):
                    fresh = agent_candidates(ipc['request'](sway, 4), ApplicationResolver())
                    commit_target = state.commit_target(fresh)
            except (OSError, ValueError, RuntimeError):
                # A compositor exit or malformed/replaced tree cancels safely.
                commit_target = None
        running = False
        popup.close()

    def enter_mode():
        nonlocal mode_active
        try:
            ipc['command'](sway, 'mode "agent-switcher"')
            mode_active = True
        except (OSError, ValueError, RuntimeError):
            finish('cancel')

    popup = Popup(state, finish, enter_mode)
    control.setblocking(False)

    def receive_commands(_source, _condition):
        while True:
            try:
                command = control.recv(32).decode()
            except BlockingIOError:
                break
            if command in COMMANDS:
                finish(command)
            if not running:
                return False
        return True

    popup.GLib.io_add_watch(control.fileno(), popup.GLib.IO_IN, receive_commands)
    try:
        popup.show()
        popup.Gtk.main()
    finally:
        if mode_active:
            try:
                if switcher_mode(ipc['request'](sway, 12)):
                    ipc['command'](sway, 'mode "default"')
            except (OSError, ValueError, RuntimeError):
                pass
        popup.close()
    return commit_target


def main(action):
    if action not in COMMANDS:
        raise ValueError('action must be next, previous, commit, or cancel')
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    if runtime.stat().st_uid != os.getuid() or runtime.stat().st_mode & 0o077:
        raise RuntimeError('XDG_RUNTIME_DIR must be an owned private directory')
    ipc = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'bin/mbp-intel-workspaces'))
    sway = ipc['find_socket'](runtime)
    ipc['prepare_directory'](runtime)
    address, lock_path = _runtime_paths(runtime, sway)
    try:
        _send(address, action)
        return
    except (FileNotFoundError, ConnectionRefusedError):
        if action in ('commit', 'cancel'):
            return

    target = None
    with lock_path.open('a') as lock:
        if not claim_or_forward(lock, address, action):
            return
        address.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.bind(str(address))
            try:
                target = _run_server(action, ipc, sway, control)
            finally:
                address.unlink(missing_ok=True)
    # The socket, lock and exclusive layer are all gone before focusing, so
    # compositor restoration cannot undo focus and a new gesture cannot be lost.
    if target is not None:
        _focus(ipc, sway, target)
