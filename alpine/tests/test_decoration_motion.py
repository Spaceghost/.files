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
