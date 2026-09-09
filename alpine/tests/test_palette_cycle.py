"""Palette cycling: colour that moves while the picture holds still."""
from pathlib import Path
import sys
import unittest

import numpy as np

LIBRARY = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'
sys.path.insert(0, str(LIBRARY))

import palette_cycle as cycle  # noqa: E402


def ramp_image(base, count, *, rows=8, grey_columns=0):
    """A picture of one colour ramp, optionally beside a band of greys."""
    columns = []
    for step in range(count):
        amount = (step + 1) / (count + 1)
        columns.append([round(channel * amount) for channel in base])
    for step in range(grey_columns):
        level = 30 + step * 25
        columns.append([level, level, level])
    return np.tile(np.array(columns, dtype=np.uint8), (rows, 1, 1))


class PosteriseTests(unittest.TestCase):
    def test_depth_reduces_levels_and_keeps_the_ends_intact(self):
        gradient = np.arange(256, dtype=np.uint8).reshape(1, 256, 1).repeat(3, axis=2)
        for depth, expected in ((8, (8, 8, 4)), (16, (32, 64, 32)), (24, (256, 256, 256))):
            with self.subTest(depth=depth):
                reduced = cycle.posterise(gradient, depth)
                for channel, levels in enumerate(expected):
                    self.assertEqual(len(np.unique(reduced[..., channel])), levels)
                self.assertEqual(reduced[0, 0].tolist(), [0, 0, 0])
                self.assertEqual(reduced[0, 255].tolist(), [255, 255, 255])

    def test_an_unknown_depth_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError):
            cycle.posterise(np.zeros((2, 2, 3), dtype=np.uint8), 12)


class QuantiseTests(unittest.TestCase):
    def test_indices_stay_inside_the_palette_it_returns(self):
        image = ramp_image((40, 120, 220), 12, grey_columns=4)
        indices, palette = cycle.quantise(image, 8)
        self.assertLessEqual(len(palette), 8)
        self.assertEqual(indices.shape, image.shape[:2])
        self.assertLess(int(indices.max()), len(palette))

    def test_a_palette_needs_at_least_two_colours(self):
        with self.assertRaises(ValueError):
            cycle.quantise(np.zeros((4, 4, 3), dtype=np.uint8), 1)


class RampTests(unittest.TestCase):
    def test_the_ramp_is_the_coloured_family_and_never_the_greys(self):
        image = ramp_image((30, 90, 240), 10, grey_columns=6)
        indices, palette = cycle.quantise(image, 12)
        ramp = cycle.find_ramp(palette, indices)

        self.assertGreaterEqual(len(ramp), cycle.MIN_RAMP)
        _angle, magnitude = cycle._chroma(palette)
        for entry in ramp:
            self.assertGreaterEqual(magnitude[entry], cycle.GREY_CHROMA)

    def test_a_picture_with_nothing_to_cycle_cycles_nothing(self):
        grey = np.tile(np.arange(0, 240, 20, dtype=np.uint8).reshape(1, 12, 1), (8, 1, 3))
        indices, palette = cycle.quantise(grey, 8)

        self.assertEqual(cycle.find_ramp(palette, indices), [])

    def test_the_ramp_is_ordered_from_dark_to_light(self):
        image = ramp_image((240, 80, 30), 14)
        indices, palette = cycle.quantise(image, 10)
        ramp = cycle.find_ramp(palette, indices)
        brightness = cycle._luminance(palette)[ramp]

        self.assertTrue(np.all(np.diff(brightness) >= 0), brightness)

    def test_a_run_too_small_to_see_is_left_alone(self):
        image = ramp_image((30, 90, 240), 10)
        indices, palette = cycle.quantise(image, 10)

        self.assertEqual(cycle.find_ramp(palette, indices, minimum=99), [])


class LoopTests(unittest.TestCase):
    def test_the_loop_walks_up_and_back_so_its_ends_meet(self):
        self.assertEqual(cycle.cycle_loop([1, 2, 3, 4]), [1, 2, 3, 4, 3, 2])
        # Nothing to reflect: two entries are already their own loop.
        self.assertEqual(cycle.cycle_loop([1, 2]), [1, 2])

    def test_every_step_of_the_loop_moves_one_position_only(self):
        loop = cycle.cycle_loop([0, 1, 2, 3, 4])
        for first, second in zip(loop, loop[1:] + loop[:1]):
            self.assertEqual(abs(first - second), 1, (first, second))


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.image = ramp_image((30, 90, 240), 12, grey_columns=5)
        self.cycle = cycle.prepare(self.image, depth=24, colors=12, substeps=3)

    def test_the_first_step_is_the_painting_as_it_was_quantised(self):
        canvas = cycle.apply_step(self.cycle, 0)

        self.assertTrue(np.array_equal(canvas, self.cycle['base']))

    def test_nothing_outside_the_ramp_ever_changes_colour(self):
        held = np.setdiff1d(np.arange(self.cycle['base'].size), self.cycle['moving'])
        original = self.cycle['base'][held]
        canvas = self.cycle['base'].copy()
        for step in range(len(self.cycle['palettes'])):
            cycle.apply_step(self.cycle, step, canvas)
            self.assertTrue(np.array_equal(canvas[held], original), step)

    def test_the_cycle_returns_to_where_it_started(self):
        canvas = self.cycle['base'].copy()
        for step in range(1, len(self.cycle['palettes'])):
            cycle.apply_step(self.cycle, step, canvas)
            if step == 1:
                self.assertFalse(np.array_equal(canvas, self.cycle['base']))
        cycle.apply_step(self.cycle, len(self.cycle['palettes']), canvas)

        self.assertTrue(np.array_equal(canvas, self.cycle['base']))

    def test_interpolation_keeps_each_frame_a_small_change(self):
        smooth = cycle.prepare(self.image, depth=24, colors=12, substeps=8)
        stepped = cycle.prepare(self.image, depth=24, colors=12, substeps=1)

        def largest(prepared):
            pairs = zip(prepared['palettes'], prepared['palettes'][1:])
            return max(int(np.abs(((a.astype(np.int64) >> shift) & 255)
                                  - ((b.astype(np.int64) >> shift) & 255)).max())
                       for a, b in pairs for shift in (16, 8, 0))

        self.assertLess(largest(smooth), largest(stepped))

    def test_reversing_walks_the_same_colours_the_other_way(self):
        forward = cycle.prepare(self.image, depth=24, colors=12, substeps=1)
        backward = cycle.prepare(self.image, depth=24, colors=12, substeps=1, reverse=True)

        self.assertEqual(len(forward['palettes']), len(backward['palettes']))
        self.assertTrue(np.array_equal(forward['palettes'][0], backward['palettes'][0]))
        self.assertTrue(np.array_equal(forward['palettes'][1], backward['palettes'][-1]))

    def test_a_longer_cycle_costs_palettes_rather_than_frames(self):
        def per_pixel(prepared):
            return (prepared['base'].nbytes + prepared['moving'].nbytes
                    + prepared['moving_indices'].nbytes)

        short = cycle.prepare(self.image, depth=24, colors=12, substeps=1)
        long = cycle.prepare(self.image, depth=24, colors=12, substeps=16)

        # Sixteen times the steps must cost sixteen times a few palettes, not
        # sixteen stored pictures: what scales with the image does not move.
        self.assertEqual(per_pixel(short), per_pixel(long))
        self.assertEqual(len(long['palettes']), 16 * len(short['palettes']))
        for table in long['palettes']:
            self.assertEqual(table.shape, (len(long['palette']),))


if __name__ == '__main__':
    unittest.main()
