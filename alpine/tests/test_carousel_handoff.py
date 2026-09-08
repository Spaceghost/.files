"""Escape closes the current mode without a delayed cancel for the next gesture."""

from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'alpine/desktop/.local/lib/oldbook'))
from carousel import Controller, EventFrames
from carousel_view import Popup


class FakeLoop:
    def __init__(self):
        self.sources = {}
        self.serial = 0

    def idle_add(self, callback, *args):
        self.serial += 1
        self.sources[self.serial] = (callback, args)
        return self.serial

    def timeout_add(self, _milliseconds, callback):
        return self.idle_add(callback)

    def source_remove(self, identifier):
        self.sources.pop(identifier, None)

    def once(self):
        identifier = next(iter(self.sources))
        callback, args = self.sources.pop(identifier)
        callback(*args)

    def drain(self):
        while self.sources:
            self.once()


class CarouselHandoffTests(unittest.TestCase):
    def test_escape_bindings_have_only_synchronous_mode_handoff(self):
        source = (ROOT / 'alpine/desktop/.config/sway/local.d/window-switcher.conf').read_text()
        commands = {parts[1]: parts[2] for line in source.splitlines()
                    if len(parts := line.strip().split(None, 2)) == 3
                    and parts[0] == 'bindsym'}
        for key in ('Escape', 'Mod4+Escape', 'Mod1+Escape'):
            with self.subTest(key=key):
                self.assertEqual(commands[key], 'mode "default"')

    def test_real_mode_event_closes_popup_without_a_cancel_command(self):
        payload = b'{"change":"default"}'
        packet = struct.pack('=6sII', b'i3-ipc', len(payload), 0x80000002) + payload
        controller = Controller.__new__(Controller)
        controller.GLib = SimpleNamespace(IO_HUP=16, IO_ERR=8)
        controller.events = Mock()
        controller.events.recv.side_effect = [packet, BlockingIOError()]
        controller.frames = EventFrames()
        controller.popup = object()
        controller.mode_active = True
        controller.sway = '/private-fixture.sock'
        controller.ipc = {'request': Mock(return_value={'name': 'default'})}
        controller.dismiss = Mock()
        controller.candidates = Mock()
        self.assertTrue(controller.event(7, 1))
        controller.dismiss.assert_called_once_with()
        controller.candidates.assert_not_called()

    def focus_fixture(self, delivered_modifiers):
        loop = FakeLoop()
        popup = Popup.__new__(Popup)
        popup.closed = False
        popup._deferred = set()
        popup._keyboard_ready_callback = None
        popup._keyboard_focus_handler = None
        popup._keyboard_ready_source = None
        popup._keyboard_focus_epoch = 0
        popup.GLib = loop
        popup.modifier = 'super'
        popup.current_modifiers = Mock(return_value=set())
        display = Mock()
        display.is_closed.return_value = False
        display.sync.side_effect = lambda: setattr(popup.current_modifiers, 'return_value', delivered_modifiers)
        popup.window = Mock()
        popup.window.is_active.return_value = False
        popup.window.get_display.return_value = display
        popup.window.connect.return_value = 7
        controller = Controller.__new__(Controller)
        controller.popup, controller.modifier = popup, 'super'
        controller.GLib = loop
        controller.command = Mock()
        controller.action = Mock()
        popup.on_command = controller.action
        controller.mapped()
        return controller, popup, loop

    def activate(self, popup):
        popup.window.is_active.return_value = True
        callback = popup.window.connect.call_args.args[1]
        callback(popup.window, None)

    def test_empty_modifiers_before_keyboard_enter_never_commit(self):
        controller, popup, loop = self.focus_fixture({'Mod4'})
        loop.drain()
        controller.action.assert_not_called()
        self.activate(popup)
        loop.drain()
        popup.window.get_display().sync.assert_called_once_with()
        controller.action.assert_not_called()

    def test_quick_release_before_keyboard_enter_commits_after_protocol_sync(self):
        controller, popup, loop = self.focus_fixture(set())
        loop.drain()
        controller.action.assert_not_called()
        self.activate(popup)
        loop.once()
        controller.action.assert_not_called()
        loop.drain()
        controller.action.assert_called_once_with('commit')

    def test_focus_loss_after_protocol_sync_cancels_pending_initial_check(self):
        controller, popup, loop = self.focus_fixture(set())
        self.activate(popup)
        loop.once()
        popup.window.is_active.return_value = False
        popup.window.connect.call_args.args[1](popup.window, None)
        loop.drain()
        controller.action.assert_not_called()

    def test_actual_modifier_release_still_commits_after_a_held_focus_entry(self):
        controller, popup, loop = self.focus_fixture({'Mod4'})
        self.activate(popup)
        loop.drain()
        controller.action.assert_not_called()
        popup.Gdk = SimpleNamespace(keyval_name=lambda value: value)
        popup._key_released(None, 'Super_L', 0, 0)
        popup.current_modifiers.return_value = set()
        loop.drain()
        controller.action.assert_called_once_with('commit')

    def test_close_discards_pending_keyboard_ready_callback(self):
        controller, popup, loop = self.focus_fixture(set())
        self.activate(popup)
        loop.once()
        popup._tick_id, popup._theme_timer = None, 0
        popup.Gtk, popup.provider = Mock(), object()
        popup._textures, popup._card_nodes = {}, {}
        popup._unavailable, popup._layouts = set(), {}
        popup.close()
        loop.drain()
        controller.action.assert_not_called()
        self.assertIsNone(popup._keyboard_ready_callback)
        popup.window.disconnect.assert_called_once_with(7)


if __name__ == '__main__':
    unittest.main()
