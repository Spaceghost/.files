"""Interactive lifecycle tests without GTK or real keyboard devices."""
from concurrent.futures import Future
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from superhold.config import AppConfig
from superhold.shortcut_hold import HoldState, KEY_LEFTMETA
from superhold.shortcut_controller import InteractiveController
from superhold.shortcut_overlay import GraphicalSessionGuard


class Executor:
    def __init__(self):
        self.jobs = []
    def submit(self, fn, *args):
        future = Future()
        self.jobs.append((future, fn, args))
        return future
    def finish(self):
        future, fn, args = self.jobs.pop(0)
        if not future.cancelled():
            future.set_result(fn(*args))


class Monitor:
    def __init__(self):
        self.state = HoldState()
        self.device_count = 1
        self.input_synced = True
    def poll(self, now):
        return self.state.visible(now)
    def close(self):
        pass


class Overlay:
    def __init__(self):
        self.shown = []
        self.errors = []
    def show(self, snapshot):
        self.shown.append(snapshot)
    def hide(self):
        pass
    def close(self):
        pass
    def show_error(self, message):
        self.errors.append(message)


class Context:
    active = True
    def alive(self):
        return self.active
    def allows_overlay(self, now):
        return self.active
    def close(self):
        pass


class Provider:
    def snapshot(self):
        return {'app': 'Editor', 'target': {'con_id': 4}, 'sections': []}


class Sender:
    def __init__(self):
        self.calls = []
    def send(self, target, action):
        self.calls.append((target, action))
        return {'ok': True, 'error': ''}


class InteractiveTests(unittest.TestCase):
    def setUp(self):
        self.monitor, self.overlay, self.context = Monitor(), Overlay(), Context()
        self.executor, self.sender = Executor(), Sender()
        self.controller = InteractiveController(
            self.monitor, Provider(), self.overlay, self.context, self.context,
            config=AppConfig(), sender=self.sender, executor=self.executor,
            action_executor=self.executor)
        self.addCleanup(self.controller.close)
    def key(self, code, down, now):
        self.monitor.state.update('keyboard', code, int(down), now)
    def open(self):
        self.key(KEY_LEFTMETA, True, 0)
        self.controller.tick(.6)
        self.executor.finish()
        self.controller.tick(.7)
    def test_sticky_survives_release_and_freezes_context(self):
        self.open()
        self.key(KEY_LEFTMETA, False, .8)
        self.controller.tick(.8)
        self.controller.tick(20)
        self.assertTrue(self.controller.visible)
        self.assertEqual(len(self.overlay.shown), 1)
        self.assertEqual(self.executor.jobs, [])
        self.controller.dismiss()
        self.assertFalse(self.controller.visible)
    def test_release_while_loading_still_opens_sticky(self):
        self.key(KEY_LEFTMETA, True, 0)
        self.controller.tick(.6)
        self.assertEqual(self.overlay.shown, [])
        self.key(KEY_LEFTMETA, False, .65)
        self.controller.tick(.7)
        self.executor.finish()
        self.controller.tick(.8)
        self.assertTrue(self.controller.visible)
    def test_chord_cancels_pending_snapshot_even_after_release(self):
        self.key(KEY_LEFTMETA, True, 0)
        self.controller.tick(.6)
        self.key(30, True, .61)
        self.key(30, False, .62)
        self.key(KEY_LEFTMETA, False, .63)
        self.controller.tick(.7)
        self.executor.finish()
        self.controller.tick(.8)
        self.assertEqual(self.overlay.shown, [])
    def test_release_mode_hides(self):
        self.controller.configure(AppConfig(dismiss_mode='release'))
        self.open()
        self.key(KEY_LEFTMETA, False, .8)
        self.controller.tick(.8)
        self.assertFalse(self.controller.visible)
    def test_click_waits_for_super_and_enter_release(self):
        self.open()
        self.key(28, True, .71)
        action = {'label': 'Save', 'sequence': [{'key': 's', 'modifiers': ['ctrl']}]}
        self.controller.activate(action, now=.72)
        self.controller.tick(.8)
        self.assertEqual(self.sender.calls, [])
        self.key(KEY_LEFTMETA, False, .9)
        self.controller.tick(1)
        self.assertEqual(self.executor.jobs, [])
        self.key(28, False, 1.1)
        self.controller.tick(1.2)
        self.executor.finish()
        self.controller.tick(1.3)
        self.assertEqual(self.sender.calls, [({'con_id': 4}, action)])
        self.assertFalse(self.controller.visible)
    def test_enter_received_by_gtk_before_evdev_waits_for_release(self):
        self.open()
        self.key(KEY_LEFTMETA, False, .71)
        self.controller.tick(.72)
        original_poll = self.monitor.poll
        queued = [(28, True)]
        def delayed_poll(now):
            for code, down in queued:
                self.key(code, down, now)
            queued.clear()
            return original_poll(now)
        self.monitor.poll = delayed_poll
        action = {'label': 'Save', 'sequence': [{'key': 's', 'modifiers': ['ctrl']}]}
        self.controller.activate(action, now=.73)
        self.assertFalse(self.controller.dispatch_safe())
        self.controller.tick(.8)
        self.assertFalse(self.overlay.errors)
        self.assertEqual(self.executor.jobs, [])
        self.key(28, False, .9)
        self.controller.tick(1)
        self.executor.finish()
        self.assertEqual(self.sender.calls, [({'con_id': 4}, action)])

    def test_input_resync_after_click_cancels_even_when_no_key_remains_down(self):
        self.open()
        self.controller.activate({'label': 'Save'}, now=.75)
        self.key(KEY_LEFTMETA, False, .8)
        self.monitor.state._resync_device('keyboard', set())
        self.controller.tick(.9)
        self.assertEqual(self.executor.jobs, [])
        self.assertFalse(self.controller.dispatch_safe())
        self.assertTrue(self.overlay.errors)

    def test_poll_error_during_activation_closes_without_queuing_input(self):
        self.open()
        def failed_poll(now):
            raise OSError('input device failed')
        self.monitor.poll = failed_poll
        self.controller.activate({'label': 'Save'}, now=.75)
        self.assertTrue(self.controller.closed)
        self.assertEqual(self.executor.jobs, [])
        self.assertEqual(self.sender.calls, [])

    def test_new_input_cancels_queued_action(self):
        self.open()
        self.controller.activate({'label': 'Save'}, now=.75)
        self.key(30, True, .8)
        self.key(30, False, .81)
        self.key(KEY_LEFTMETA, False, .82)
        self.controller.tick(.9)
        self.assertEqual(self.executor.jobs, [])
        self.assertEqual(self.sender.calls, [])
        self.assertTrue(self.overlay.errors)
    def test_locked_session_cancels_queued_action(self):
        self.open()
        self.controller.activate({'label': 'Save'}, now=.75)
        self.context.active = False
        self.key(KEY_LEFTMETA, False, .8)
        self.controller.tick(.9)
        self.assertEqual(self.executor.jobs, [])
        self.assertEqual(self.sender.calls, [])
    def test_timeout_and_unread_input_do_not_dispatch(self):
        self.open()
        self.controller.activate({'label': 'Save'}, now=.75)
        self.key(KEY_LEFTMETA, False, .8)
        self.monitor.input_synced = False
        self.controller.tick(1)
        self.assertEqual(self.executor.jobs, [])
        self.controller.tick(6)
        self.assertTrue(self.overlay.errors)
        self.assertEqual(self.sender.calls, [])
    def test_manual_open_is_sticky_even_with_release_setting(self):
        self.controller.configure(AppConfig(dismiss_mode='release'))
        self.controller.request_open()
        self.controller.tick(0)
        self.executor.finish()
        self.controller.tick(.1)
        self.assertTrue(self.controller.visible)
    def initial_guard(self, locked=False):
        guard = GraphicalSessionGuard(
            '/unused', '/unused/wayland', activity_probe=lambda: False,
            lock_probe=lambda *_args: locked)
        future = Future()
        guard._future = future
        self.controller.guard = guard
        return guard, future

    def test_manual_request_is_busy_before_first_tick(self):
        self.controller.request_open()
        self.assertTrue(self.controller.busy)

    def test_manual_open_waits_for_first_real_guard_probe_then_shows_context(self):
        guard, future = self.initial_guard()
        self.controller.request_open()
        self.controller.tick(0)
        self.assertTrue(self.controller.busy)
        self.assertFalse(self.controller.visible)
        self.assertEqual(self.executor.jobs, [])
        future.set_result(True)
        self.controller.tick(.1)
        self.assertTrue(guard.ready)
        self.executor.finish()
        self.controller.tick(.2)
        self.assertTrue(self.controller.visible)

    def test_manual_open_does_not_wait_through_a_completed_inactive_probe(self):
        guard, future = self.initial_guard()
        self.controller.request_open()
        self.controller.tick(0)
        future.set_result(False)
        self.controller.tick(.1)
        self.assertTrue(guard.ready)
        self.assertFalse(self.controller.busy)
        self.assertEqual(self.executor.jobs, [])

    def test_manual_request_wait_is_bounded_and_never_survives_a_lock(self):
        guard, future = self.initial_guard()
        self.controller.request_open()
        self.controller.tick(0)
        self.controller.tick(1.9)
        self.assertTrue(self.controller.busy)
        future.set_result(True)
        self.controller.tick(2.1)
        self.assertFalse(self.controller.busy)
        self.assertEqual(self.executor.jobs, [])
        guard.close()
        guard, future = self.initial_guard(locked=True)
        self.controller.request_open()
        self.controller.tick(3)
        self.assertFalse(self.controller.busy)
        self.assertEqual(self.executor.jobs, [])

    def test_compositor_exit_clears_manual_request_wait(self):
        self.initial_guard()
        self.controller.request_open()
        self.controller.tick(0)
        self.context.active = False
        self.assertFalse(self.controller.tick(.1))
        self.assertTrue(self.controller.closed)
        self.assertFalse(self.controller.busy)

    def test_no_readable_keyboard_prevents_replay(self):
        self.open()
        self.monitor.device_count = 0
        self.controller.activate({'label': 'Save'}, now=.75)
        self.key(KEY_LEFTMETA, False, .8)
        self.controller.tick(6)
        self.assertEqual(self.sender.calls, [])
        self.assertTrue(self.overlay.errors)


if __name__ == '__main__':
    unittest.main()
