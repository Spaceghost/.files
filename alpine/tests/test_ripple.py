"""The ripple's geometry, timing and power policy, checked without a GPU."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import power_source
import ripple


class Region(unittest.TestCase):
    def test_bottom_edge_takes_a_fraction_of_the_output_from_its_own_side(self):
        rect = ripple.region({'x': 0, 'y': 0, 'width': 1200, 'height': 900}, 'bottom', 1 / 3)
        self.assertEqual(rect, {'x': 0, 'y': 600, 'width': 1200, 'height': 300})

    def test_right_edge_takes_a_fraction_of_the_output_from_its_own_side(self):
        rect = ripple.region({'x': 0, 'y': 0, 'width': 1200, 'height': 900}, 'right', 1 / 4)
        self.assertEqual(rect, {'x': 900, 'y': 0, 'width': 300, 'height': 900})

    def test_offset_outputs_carry_their_offset_into_the_region(self):
        rect = ripple.region({'x': 1200, 'y': 300, 'width': 800, 'height': 600}, 'bottom', 0.5)
        self.assertEqual(rect, {'x': 1200, 'y': 600, 'width': 800, 'height': 300})

    def test_unknown_edge_is_rejected(self):
        with self.assertRaises(ValueError):
            ripple.region({'x': 0, 'y': 0, 'width': 100, 'height': 100}, 'top')

    def test_fraction_is_clamped_to_something_drawable(self):
        rect = ripple.region({'x': 0, 'y': 0, 'width': 100, 'height': 100}, 'bottom', 10.0)
        self.assertEqual(rect, {'x': 0, 'y': 0, 'width': 100, 'height': 100})


class Origin(unittest.TestCase):
    def test_starts_at_the_middle_of_the_landed_edge(self):
        area = {'x': 0, 'y': 600, 'width': 1200, 'height': 300}
        point = ripple.origin({'x': 500, 'y': 600, 'width': 200, 'height': 40}, area)
        self.assertEqual(point, (0.5, 0.0))

    def test_is_relative_to_the_region_not_the_output(self):
        area = {'x': 900, 'y': 0, 'width': 300, 'height': 900}
        point = ripple.origin({'x': 900, 'y': 450, 'width': 300, 'height': 40}, area)
        self.assertEqual(point[0], 0.5)
        self.assertAlmostEqual(point[1], 0.5)

    def test_stays_inside_the_region_even_if_the_strip_does_not(self):
        area = {'x': 0, 'y': 0, 'width': 400, 'height': 200}
        point = ripple.origin({'x': -100, 'y': -50, 'width': 40, 'height': 20}, area)
        self.assertEqual(point, (0.0, 0.0))


class Policy(unittest.TestCase):
    def test_never_draws_with_animations_off(self):
        self.assertFalse(ripple.allowed(animations=False, current='mains'))

    def test_follows_the_shaders_rung_of_the_power_ladder(self):
        for posture in power_source.POSTURES:
            self.assertEqual(ripple.allowed(animations=True, current=posture),
                             power_source.allows(ripple.EFFECT, current=posture))

    def test_registered_at_mains_like_every_other_shader_effect(self):
        self.assertTrue(power_source.allows(ripple.EFFECT, current='mains'))
        self.assertFalse(power_source.allows(ripple.EFFECT, current='battery'))


class Wave(unittest.TestCase):
    def test_visibility_peaks_at_the_strike_itself(self):
        self.assertEqual(ripple.visibility(0.0, 0.0), 1.0)

    def test_visibility_is_zero_before_the_strike_and_after_the_wave_ends(self):
        self.assertEqual(ripple.visibility(0.0, -0.01), 0.0)
        self.assertEqual(ripple.visibility(0.0, ripple.DURATION + 0.01), 0.0)

    def test_visibility_follows_the_travelling_front(self):
        # A point half the crossing away should be most visible when the front
        # has actually reached it, not at the moment of the strike.
        distance = 0.5
        elapsed_at_front = (distance / ripple.SPEED) * ripple.DURATION
        early = ripple.visibility(distance, 0.05 * ripple.DURATION)
        at_front = ripple.visibility(distance, elapsed_at_front)
        late = ripple.visibility(distance, ripple.DURATION * 0.99)
        self.assertGreater(at_front, early)
        self.assertGreater(at_front, late)

    def test_visibility_fades_with_radial_distance_at_a_fixed_age(self):
        near = ripple.visibility(0.1, 0.1 * ripple.DURATION)
        far = ripple.visibility(2.0, 0.1 * ripple.DURATION)
        self.assertGreater(near, far)

    def test_visibility_rejects_a_non_positive_duration(self):
        with self.assertRaises(ValueError):
            ripple.visibility(0.0, 0.0, duration=0.0)

    def test_radial_reach_decays_monotonically(self):
        values = [ripple.radial_reach(distance) for distance in (0.0, 0.5, 1.0, 2.0, 5.0)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(ripple.radial_reach(0.0), 1.0)

    def test_crest_is_bounded_by_the_amplitude(self):
        for distance in (0.0, 0.2, 0.5, 1.0, 2.0):
            for step in range(0, 11):
                elapsed = ripple.DURATION * step / 10
                self.assertLessEqual(abs(ripple.crest(distance, elapsed)), ripple.AMPLITUDE + 1e-9)

    def test_crest_is_silent_outside_its_lifetime(self):
        self.assertEqual(ripple.crest(0.3, -0.01), 0.0)
        self.assertEqual(ripple.crest(0.3, ripple.DURATION + 0.01), 0.0)

    def test_crest_rejects_a_non_positive_duration(self):
        with self.assertRaises(ValueError):
            ripple.crest(0.0, 0.0, duration=0.0)


class PortablePixmap(unittest.TestCase):
    def test_round_trips_a_bare_header(self):
        body = b'\x01\x02\x03' * 6
        data = b'P6 3 2 255\n' + body
        width, height, offset = ripple.parse_ppm(data)
        self.assertEqual((width, height), (3, 2))
        self.assertEqual(data[offset:], body)

    def test_skips_comments_in_the_header(self):
        data = b'P6\n# grim\n4 1\n255\n' + b'\xff' * 12
        width, height, offset = ripple.parse_ppm(data)
        self.assertEqual((width, height), (4, 1))

    def test_rejects_anything_but_eight_bit_binary(self):
        with self.assertRaises(ValueError):
            ripple.parse_ppm(b'P3 1 1 255\n')

    def test_rejects_an_empty_image(self):
        with self.assertRaises(ValueError):
            ripple.parse_ppm(b'P6 0 1 255\n')


class Crop(unittest.TestCase):
    def _pixmap(self, width, height, fill):
        """A tiny binary PPM whose pixel (x, y) is a distinct, checkable value."""
        body = bytearray(width * height * 3)
        for y in range(height):
            for x in range(width):
                index = (y * width + x) * 3
                body[index:index + 3] = fill(x, y)
        return b'P6 %d %d 255\n' % (width, height) + bytes(body), len(b'P6 %d %d 255\n' % (width, height))

    def test_takes_the_region_at_scale_one_unchanged(self):
        data, offset = self._pixmap(4, 4, lambda x, y: bytes((x * 10, y * 10, 0)))
        pixels, span, thickness = ripple.crop(data, offset, 4, 4, {'x': 1, 'y': 1, 'width': 2, 'height': 2})
        self.assertEqual((span, thickness), (2, 2))
        # Row 0 of the crop is the bottom of the requested area (y=2 of the source).
        self.assertEqual(tuple(pixels[0, 0]), (10, 20, 0))

    def test_a_logical_area_is_scaled_up_to_the_photographs_real_pixels(self):
        # A HiDPI output: the area is in logical units (as Sway reports outputs
        # in) but the photograph -- like grim's -- is at physical resolution.
        width, height, scale = 8, 8, 2.0
        data, offset = self._pixmap(width, height, lambda x, y: bytes((x * 10, y * 10, 0)))
        logical_area = {'x': 1, 'y': 1, 'width': 2, 'height': 2}
        pixels, span, thickness = ripple.crop(data, offset, width, height, logical_area, scale)
        # At scale 2, a 2x2 logical area becomes the 4x4 physical block at (2, 2).
        self.assertEqual((span, thickness), (4, 4))
        self.assertEqual(tuple(pixels[-1, 0]), (20, 20, 0))

    def test_scale_one_is_the_default_and_matches_no_scale_argument(self):
        data, offset = self._pixmap(6, 6, lambda x, y: bytes((x, y, x + y)))
        area = {'x': 2, 'y': 2, 'width': 3, 'height': 3}
        without = ripple.crop(data, offset, 6, 6, area)
        with_default = ripple.crop(data, offset, 6, 6, area, 1.0)
        self.assertEqual(without[1:], with_default[1:])
        self.assertTrue((without[0] == with_default[0]).all())

    def test_never_reads_past_the_photograph_even_if_the_scaled_area_would(self):
        data, offset = self._pixmap(4, 4, lambda x, y: bytes((1, 1, 1)))
        pixels, span, thickness = ripple.crop(data, offset, 4, 4,
                                              {'x': 0, 'y': 0, 'width': 10, 'height': 10}, 2.0)
        self.assertEqual((span, thickness), (4, 4))
        self.assertEqual(pixels.shape, (4, 4, 3))


if __name__ == '__main__':
    unittest.main()
