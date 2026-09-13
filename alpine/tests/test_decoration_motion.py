"""Decoration motion stays smooth across frame rates and changing targets."""

import importlib.util
from pathlib import Path
import unittest


MODEL = (Path(__file__).resolve().parents[1]
         / 'desktop/.local/lib/oldbook/decoration_motion.py')
SPEC = importlib.util.spec_from_file_location('decoration_motion', MODEL)
motion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(motion)


class DecorationMotionTests(unittest.TestCase):
    def trajectory(self, frequency):
        value = velocity = 0.0
        samples = []
        for frame in range(frequency // 5):
            value, velocity = motion.advance(value, velocity, 240, 1 / frequency)
            if (frame + 1) % (frequency // 60) == 0:
                samples.append((value, velocity))
        return samples

    def test_60_and_120_hz_follow_the_same_trajectory(self):
        sixty = self.trajectory(60)
        one_twenty = self.trajectory(120)
        self.assertEqual(len(sixty), len(one_twenty))
        for first, second in zip(sixty, one_twenty):
            self.assertAlmostEqual(first[0], second[0], places=9)
            self.assertAlmostEqual(first[1], second[1], places=9)
        self.assertGreater(sixty[-1][0], 239)

    def test_retarget_keeps_motion_bounded_in_both_directions(self):
        value = velocity = 0.0
        for target in (100, 180, 25, -80, 160):
            for _ in range(8):
                previous = value
                value, velocity = motion.advance(value, velocity, target, 1 / 60)
                self.assertGreaterEqual(value, min(previous, target))
                self.assertLessEqual(value, max(previous, target))
        # Even a target placed immediately ahead of large existing momentum
        # cannot be crossed and oscillate back.
        self.assertEqual(motion.advance(50, 10000, 50.1, 1 / 60), (50.1, 0))

    def test_moving_target_trajectories_remain_consistent_at_60_and_120_hz(self):
        def follow(frequency):
            value = velocity = 0.0
            samples = []
            for frame in range(frequency // 2):
                # The compositor supplies the same 60 Hz targets to either
                # frame clock. A 120 Hz display adds intermediate frames.
                target = ((frame // (frequency // 60)) + 1) * 8
                value, velocity = motion.advance(value, velocity, target,
                                                 1 / frequency)
                if (frame + 1) % (frequency // 60) == 0:
                    samples.append(value)
            return samples

        for first, second in zip(follow(60), follow(120)):
            self.assertAlmostEqual(first, second, places=9)

    def test_rectangle_settles_exactly_and_keeps_positive_dimensions(self):
        current = {'x': -500, 'y': 20, 'width': 800, 'height': 600}
        target = {'x': -420, 'y': 600, 'width': 340, 'height': 28}
        velocity = {}
        for _ in range(120):
            current, velocity, settled = motion.advance_rect(
                current, velocity, target, 1 / 120)
            self.assertGreater(current['width'], 0)
            self.assertGreater(current['height'], 0)
            if settled:
                break
        self.assertTrue(settled)
        self.assertEqual(current, target)
        self.assertEqual(set(velocity.values()), {0})

    def test_stalled_frame_is_bounded_and_zero_time_preserves_motion(self):
        self.assertEqual(motion.advance(0, 5, 100, 3),
                         motion.advance(0, 5, 100, 0.05))
        self.assertEqual(motion.advance(0, 5, 100, 0), (0, 5))

    def test_a_settling_spring_overshoots_once_and_comes_to_rest_exactly(self):
        """The landing a released strip makes, and the only place it is wanted.

        A critically damped spring stops dead, which reads as the strip being
        placed rather than arriving. Below one it passes the target and comes
        back, and the rebound is a fraction of the distance travelled, so the
        same number holds whatever the flight length.
        """
        for distance in (120.0, 400.0):
            value = velocity = 0.0
            peak = 0.0
            for _ in range(600):
                value, velocity = motion.advance(value, velocity, distance,
                                                 1 / 120, response=0.28,
                                                 damping=0.82)
                peak = max(peak, value)
            self.assertGreater(peak, distance, 'the landing did not overshoot')
            self.assertLess(peak - distance, distance * 0.02)
            self.assertEqual((value, velocity), (distance, 0.0))

    def test_settling_and_critical_springs_agree_across_frame_rates(self):
        def run(frequency, damping):
            value = velocity = 0.0
            samples = []
            for frame in range(frequency // 2):
                value, velocity = motion.advance(value, velocity, 300, 1 / frequency,
                                                 damping=damping)
                if (frame + 1) % (frequency // 60) == 0:
                    samples.append(value)
            return samples

        for damping in (1.0, 0.82):
            for first, second in zip(run(60, damping), run(120, damping)):
                self.assertAlmostEqual(first, second, places=9)

    def test_damping_outside_its_range_is_refused(self):
        for damping in (0, -0.5, 1.5):
            with self.subTest(damping=damping), self.assertRaises(ValueError):
                motion.advance(0, 0, 10, 1 / 60, damping=damping)

    def test_opacity_uses_a_small_tolerance_and_settles_at_exact_target(self):
        value = velocity = 0.0
        for _ in range(120):
            previous = value
            value, velocity = motion.advance(value, velocity, 0.67, 1 / 120,
                                             tolerance=0.0001)
            self.assertGreaterEqual(value, previous)
            self.assertLessEqual(value, 0.67)
        self.assertEqual((value, velocity), (0.67, 0))


if __name__ == '__main__':
    unittest.main()


class ContactTests(unittest.TestCase):
    """The strike fires when the strip first reaches home, not when it settles."""
    FLIGHT = dict(response=0.18, tolerance=0.5, damping=0.82)

    def flight(self, distance, frequency=60):
        """One docked landing: y falls `distance` px onto the band, width grows."""
        departure = {'x': 200.0, 'y': 848.0 - distance, 'width': 600.0, 'height': 34.0}
        target = {'x': 18.0, 'y': 848.0, 'width': 1404.0, 'height': 34.0}
        signs = motion.approach_signs(departure, target)
        rect, velocity = dict(departure), {}
        contact = settled = None
        for frame in range(1, 600):
            rect, velocity, done = motion.advance_rect(rect, velocity, target, 1 / frequency,
                                                       **self.FLIGHT)
            if contact is None and motion.contact(rect, target, signs):
                contact = frame
            if done:
                settled = frame
                break
        return signs, contact, settled

    def test_signs_say_which_way_each_coordinate_sets_out(self):
        signs = motion.approach_signs({'x': 10, 'y': 500, 'width': 600, 'height': 34.4},
                                      {'x': 18, 'y': 848, 'width': 1404, 'height': 34})
        self.assertEqual(signs, {'x': -1, 'y': -1, 'width': -1, 'height': 0})

    def test_contact_is_the_first_frame_home_and_the_settle_comes_much_later(self):
        for distance in (60, 150, 300, 500):
            with self.subTest(distance=distance):
                signs, contact, settled = self.flight(distance)
                self.assertIsNotNone(contact)
                self.assertIsNotNone(settled)
                # Arrival is a fifth of a second in; the rebound and settle
                # add at least another 150 ms, which the wave no longer waits for.
                self.assertLessEqual(contact, 13)
                self.assertGreaterEqual(settled - contact, 9)

    def test_a_strip_still_on_its_way_has_not_made_contact(self):
        target = {'x': 18, 'y': 848, 'width': 1404, 'height': 34}
        signs = motion.approach_signs({'x': 200, 'y': 500, 'width': 600, 'height': 34}, target)
        self.assertFalse(motion.contact({'x': 19, 'y': 840, 'width': 1404, 'height': 34},
                                        target, signs))
        # Within the tolerance, or past the target, counts as arrived.
        self.assertTrue(motion.contact({'x': 18.6, 'y': 847.2, 'width': 1403.5, 'height': 34},
                                       target, signs))
        self.assertTrue(motion.contact({'x': 17, 'y': 851, 'width': 1406, 'height': 34},
                                       target, signs))

    def test_a_coordinate_with_nowhere_to_go_never_blocks_contact(self):
        target = {'x': 18, 'y': 848, 'width': 1404, 'height': 34}
        signs = motion.approach_signs(dict(target, y=500), target)
        self.assertEqual([key for key, sign in signs.items() if sign], ['y'])
        self.assertTrue(motion.contact(dict(target, y=848.4), target, signs))
        self.assertFalse(motion.contact(dict(target, y=700), target, signs))

    def test_contact_agrees_across_frame_rates(self):
        _, at_60, _ = self.flight(300, 60)
        _, at_120, _ = self.flight(300, 120)
        self.assertAlmostEqual(at_60 / 60, at_120 / 120, delta=1 / 60)
