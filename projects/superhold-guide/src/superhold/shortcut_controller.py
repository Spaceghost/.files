"""Focus-aware browsing and deferred native shortcut activation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import time

from .shortcut_overlay import ServiceController


class InteractiveController(ServiceController):
    """Capture before mapping, freeze while browsing, and release before sending."""

    def __init__(self, *args, config, sender, action_executor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sender = sender
        self.action_executor = action_executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='superhold-actions')
        self._owns_action_executor = action_executor is None
        self._action_future = None
        self._pending_action = None
        self._dispatch_allowed = False
        self._keys_released = False
        self._last_poll = float('-inf')
        self._open_requested = False
        self._open_probe_deadline = None
        self._manual = False
        self._hold_cancel_serial = 0
        self._action_press_serial = 0
        self._action_cancel_serial = 0
        self.configure(config)

    def configure(self, config):
        self.config = config
        self.monitor.state.threshold = config.hold_delay_ms / 1000
        self.sender.key_delay_ms = config.key_delay_ms

    @property
    def busy(self):
        return (self._open_requested or self._holding or self._pending_action is not None
                or self._action_future is not None)

    def request_open(self):
        if not self.closed and not self.busy:
            self._open_requested = True
            self._open_probe_deadline = None

    def dismiss(self):
        self._open_requested = False
        self._open_probe_deadline = None
        self._hide(cancel_hold=True)

    def dispatch_safe(self):
        """Thread-safe scalar snapshot, refreshed by the UI's nonblocking input poll."""
        return (not self.closed and self._dispatch_allowed and self.graphical_active
                and self._keys_released and time.monotonic() - self._last_poll < .15)

    def _poll_input(self, now):
        requested = bool(self.monitor.poll(now))
        self._keys_released = (self.monitor.device_count > 0
                               and self.monitor.input_synced
                               and not self.monitor.state.pressed_codes)
        self._last_poll = time.monotonic()
        return requested

    def activate(self, action, now=None):
        if not self.snapshot_ready or self._pending_action or self._action_future:
            return
        target = (self._loaded_snapshot or {}).get('target')
        if not target:
            self.overlay.show_error('The original application is unavailable. Open the guide again.')
            return
        now = time.monotonic() if now is None else now
        # GTK can deliver Enter before the periodic input callback; drain the
        # bounded monitor first so that Enter belongs to the release wait.
        try:
            self._poll_input(now)
        except (OSError, RuntimeError):
            self.close()
            return
        self._pending_action = (deepcopy(target), deepcopy(action),
                                now + self.config.release_timeout_ms / 1000)
        self._action_press_serial = self.monitor.state.press_serial
        self._dispatch_allowed = True
        self.dismiss()
        # Dismiss intentionally cancels the original Super hold. Subsequent
        # cancellation means new uncertainty (dropped input, resync, unplug).
        self._action_cancel_serial = self.monitor.state.cancel_serial

    def _abort_action(self, message=None):
        self._pending_action = None
        self._dispatch_allowed = False
        if self._action_future is not None:
            self._action_future.cancel()
        if message and self.graphical_active:
            self.overlay.show_error(message)

    def _collect_action(self, now):
        if self._action_future is not None and self._action_future.done():
            future, self._action_future = self._action_future, None
            if not future.cancelled():
                try:
                    result = future.result()
                except Exception as error:
                    result = {'ok': False, 'error': str(error)}
                if not result.get('ok') and self.graphical_active:
                    self.overlay.show_error(result.get('error') or 'Shortcut could not be sent.')
            self._dispatch_allowed = False
        if not self._pending_action:
            return
        target, action, deadline = self._pending_action
        if now >= deadline:
            self._abort_action('Shortcut cancelled: release all keys and check keyboard access.')
        elif self._keys_released:
            self._pending_action = None
            self._action_future = self.action_executor.submit(self.sender.send, target, action)

    def tick(self, now):
        if self.closed:
            return False
        if not self.liveness.alive():
            self.close()
            return False
        try:
            requested = self._poll_input(now)
            self.graphical_active = self.guard.allows_overlay(now)
        except (OSError, RuntimeError):
            self.close()
            return False
        if (self._open_requested and self._open_probe_deadline is not None
                and now >= self._open_probe_deadline):
            self.dismiss()
        if not self.graphical_active:
            self._abort_action()
            waiting_for_initial_probe = (
                self._open_requested and not getattr(self.guard, 'ready', True)
                and not getattr(self.guard, 'locked', False))
            if waiting_for_initial_probe:
                if self._open_probe_deadline is None:
                    self._open_probe_deadline = now + 2
                # Preserve only the user's initial manual-open request. Do not
                # map anything or retain a Super hold until activity is known.
                self._hide(cancel_hold=True)
            else:
                self.dismiss()
            return True
        if self._pending_action or self._action_future:
            if self.monitor.state.press_serial != self._action_press_serial:
                self._abort_action('Shortcut cancelled because another key was pressed.')
            elif self.monitor.state.cancel_serial != self._action_cancel_serial:
                self._abort_action('Shortcut cancelled because keyboard input changed or was lost.')
        self._collect_action(now)
        if self._pending_action or self._action_future:
            return True
        if self._holding:
            invalidated = self.monitor.state.cancel_serial != self._hold_cancel_serial
            release = self.config.dismiss_mode == 'release' and not self._manual and not requested
            if invalidated or release:
                self.dismiss()
                return True
        if not self._holding and (requested or self._open_requested):
            self._manual = self._open_requested
            self._open_requested = False
            self._open_probe_deadline = None
            self._holding = True
            self._hold_cancel_serial = self.monitor.state.cancel_serial
            # No focus-taking loading window: capture the app before mapping.
            self._submit_snapshot()
        self._collect_snapshot(now)
        return True

    def close(self):
        if self.closed:
            return
        self._abort_action()
        self._open_requested = False
        self._open_probe_deadline = None
        super().close()
        if self._owns_action_executor:
            self.action_executor.shutdown(wait=False, cancel_futures=True)
