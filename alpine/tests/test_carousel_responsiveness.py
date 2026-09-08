"""Exercise animation latency with the production tick and a controlled clock."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
from carousel_view import Popup


class FrameClock:
    def __init__(self):
        self.stamp = 1_000_000

    def get_frame_time(self):
        return self.stamp


class Stage:
    """Only replace GTK drawing and callback registration, not animation state."""
    def queue_draw(self):
        pass

    def add_tick_callback(self, callback):
        return 1


def popup(clock):
    view = Popup.__new__(Popup)
    view.stage = Stage()
    view.GLib = SimpleNamespace(get_monotonic_time=clock.get_frame_time)
    view.closed = False
    view.frames, view.frame_times = 0, []
    view._tick_id, view._last_frame = None, None
    view._position = view._velocity = view._reveal = view._reveal_velocity = 0.0
    view._target = 1.0
    return view


class Responsiveness(unittest.TestCase):
    def test_first_frame_shows_progress_after_request(self):
        clock = FrameClock()
        view = popup(clock)
        view._animate()
        clock.stamp += 16_667
        view._tick(view.stage, clock)
        self.assertGreater(view._reveal, .1)
        self.assertGreater(view._position, .1)

    def test_reveal_finishes_by_200_ms_and_navigation_by_300_ms(self):
        for rate in (60, 120, 144):
            with self.subTest(refresh_rate=rate):
                clock = FrameClock()
                view = popup(clock)
                view._animate()
                revealing_at_deadline = None
                for frame in range(1, round(rate * .3) + 1):
                    clock.stamp = 1_000_000 + round(frame * 1_000_000 / rate)
                    active = view._tick(view.stage, clock)
                    if frame / rate >= .2 and revealing_at_deadline is None:
                        revealing_at_deadline = view._reveal
                self.assertGreater(revealing_at_deadline, .9995)
                self.assertFalse(active)
                self.assertEqual(view._position, 1.0)

    def test_delayed_frame_catches_up_to_elapsed_time(self):
        clock = FrameClock()
        view = popup(clock)
        view._animate()
        clock.stamp += 200_000
        view._tick(view.stage, clock)
        self.assertGreater(view._reveal, .9995)
        self.assertGreater(view._position, .995)

    def test_restarting_after_idle_preserves_visible_navigation(self):
        clock = FrameClock()
        view = popup(clock)
        view._position = view._target = view._reveal = 1.0
        view._last_frame = clock.stamp - 10_000_000
        view._target = 2.0
        view._animate()
        clock.stamp += 16_667
        view._tick(view.stage, clock)
        self.assertGreater(view._position, 1.1)
        self.assertLess(view._position, 1.5)

    def test_new_input_preserves_running_animation_clock(self):
        clock = FrameClock()
        view = popup(clock)
        view._animate()
        clock.stamp += 50_000
        view._tick(view.stage, clock)
        position = view._position
        clock.stamp += 8_000
        view._target = -1.0
        view._animate()
        self.assertEqual(view._position, position)
        clock.stamp += 8_667
        view._tick(view.stage, clock)
        self.assertLess(abs(view._position - position), .3)
        clock.stamp += 500_000
        self.assertFalse(view._tick(view.stage, clock))
        self.assertEqual(view._position, -1.0)


if __name__ == '__main__':
    unittest.main()
