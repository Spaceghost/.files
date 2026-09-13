"""The ripple's geometry, timing, settings and power policy, checked without a GPU."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import power_source
import ripple

# The lower third of a 1200x900 output, and a strip docked along its bottom
# edge with the usual five-pixel margin: the case every strike on this
# desktop actually is.
AREA = {'x': 0, 'y': 600, 'width': 1200, 'height': 300}
STRIP = {'x': 5, 'y': 862, 'width': 1190, 'height': 33}
# The same strip on the right-hand edge, in the right-hand third.
SIDE_AREA = {'x': 900, 'y': 0, 'width': 300, 'height': 900}
SIDE_STRIP = {'x': 1162, 'y': 5, 'width': 33, 'height': 890}


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


class Thickness(unittest.TestCase):
    def test_is_the_bands_depth_whichever_edge_it_lies_along(self):
        self.assertEqual(ripple.thickness(AREA, 'bottom'), 300)
        self.assertEqual(ripple.thickness(SIDE_AREA, 'right'), 300)


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

    def test_a_right_hand_strip_lands_on_its_left_edge(self):
        # The edge facing the water, half way along it.
        point = ripple.origin(SIDE_STRIP, SIDE_AREA, 'right')
        self.assertAlmostEqual(point[0], (1162 - 900) / 300)
        self.assertAlmostEqual(point[1], 0.5)

    def test_stays_inside_the_region_even_if_the_strip_does_not(self):
        area = {'x': 0, 'y': 0, 'width': 400, 'height': 200}
        point = ripple.origin({'x': -100, 'y': -50, 'width': 40, 'height': 20}, area)
        self.assertEqual(point, (0.0, 0.0))


class Source(unittest.TestCase):
    def test_the_bar_is_the_strip_itself_in_units_of_the_bands_thickness(self):
        box = ripple.source(STRIP, AREA, 'bottom', 'bar', corner_radius=6)
        self.assertAlmostEqual(box['centre'][0], (5 + 595) / 300)
        self.assertAlmostEqual(box['centre'][1], (862 + 16.5 - 600) / 300)
        self.assertAlmostEqual(box['radius'], 6 / 300)
        # The half extents are of the box inside the rounding, so the strip's
        # own outline is exactly where the distance reads zero.
        self.assertAlmostEqual(box['half'][0], (595 - 6) / 300)
        self.assertAlmostEqual(box['half'][1], (16.5 - 6) / 300)

    def test_the_rounding_never_exceeds_the_strips_own_half_thickness(self):
        box = ripple.source(STRIP, AREA, 'bottom', 'bar', corner_radius=400)
        self.assertAlmostEqual(box['radius'], 16.5 / 300)
        self.assertAlmostEqual(box['half'][1], 0.0)

    def test_a_point_is_the_middle_of_the_landed_edge_with_no_extent(self):
        box = ripple.source(STRIP, AREA, 'bottom', 'point', corner_radius=6)
        self.assertEqual(box['half'], (0.0, 0.0))
        self.assertEqual(box['radius'], 0.0)
        self.assertAlmostEqual(box['centre'][0], 600 / 300)
        self.assertAlmostEqual(box['centre'][1], (862 - 600) / 300)

    def test_a_right_hand_strip_measures_in_the_bands_width(self):
        box = ripple.source(SIDE_STRIP, SIDE_AREA, 'right', 'bar')
        self.assertAlmostEqual(box['centre'][0], (1162 + 16.5 - 900) / 300)
        self.assertAlmostEqual(box['centre'][1], (5 + 445) / 300)
        point = ripple.source(SIDE_STRIP, SIDE_AREA, 'right', 'point')
        self.assertAlmostEqual(point['centre'][0], (1162 - 900) / 300)
        self.assertAlmostEqual(point['centre'][1], 450 / 300)


class Travel(unittest.TestCase):
    def test_is_the_water_between_the_landed_edge_and_the_bands_far_edge(self):
        self.assertAlmostEqual(ripple.travel(STRIP, AREA, 'bottom'), (862 - 600) / 300)
        self.assertAlmostEqual(ripple.travel(SIDE_STRIP, SIDE_AREA, 'right'), (1162 - 900) / 300)

    def test_is_held_to_something_drawable_even_if_the_strip_is_outside_the_band(self):
        self.assertEqual(ripple.travel({'x': 0, 'y': 10, 'width': 10, 'height': 10}, AREA), 0.15)
        self.assertEqual(ripple.travel({'x': 0, 'y': 2000, 'width': 10, 'height': 10}, AREA), 1.0)


class Settings(unittest.TestCase):
    def test_defaults_fill_in_when_nothing_is_set(self):
        expected = {key: (value if key in ('source', 'enabled') else float(value))
                    for key, value in ripple.DEFAULTS.items()}
        self.assertEqual(ripple.settings(), expected)
        self.assertEqual(ripple.settings(None), expected)
        self.assertEqual(ripple.settings({}), expected)

    def test_a_partial_object_keeps_the_rest_at_their_defaults(self):
        values = ripple.settings({'spacing': 30, 'source': 'point'})
        self.assertEqual(values['spacing'], 30.0)
        self.assertEqual(values['source'], 'point')
        self.assertEqual(values['duration'], ripple.DEFAULTS['duration'])

    def test_every_limit_is_inclusive_at_both_ends(self):
        for key, (low, high) in ripple.LIMITS.items():
            self.assertEqual(ripple.settings({key: low})[key], low)
            self.assertEqual(ripple.settings({key: high})[key], high)

    def test_rejects_anything_outside_the_vocabulary(self):
        invalid = [
            [], 'bar', {'sharpness': 3}, {'source': 'edge'}, {'source': None},
            {'enabled': 'yes'}, {'enabled': 1}, {'enabled': None},
            {'duration': 'long'}, {'duration': True}, {'duration': math.nan},
            {'duration': math.inf}, {'duration': 0.1}, {'duration': 3.1},
            {'reach': 0}, {'reach': 1.5}, {'spacing': 4}, {'spacing': 401},
            {'strength': -1}, {'strength': 41}, {'shade': -0.1}, {'shade': 0.5},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                ripple.settings(values)

    def test_ships_switched_on_and_can_be_switched_off(self):
        self.assertIs(ripple.settings()['enabled'], True)
        self.assertIs(ripple.settings({'enabled': False})['enabled'], False)

    def test_does_not_touch_what_it_was_given(self):
        given = {'spacing': 30}
        ripple.settings(given)
        self.assertEqual(given, {'spacing': 30})


class Plan(unittest.TestCase):
    def test_carries_the_outline_the_water_and_the_settings_in_the_bands_units(self):
        plan = ripple.plan(STRIP, AREA, 'bottom', {'spacing': 30, 'strength': 4}, corner_radius=6)
        self.assertEqual(plan['scale'], (4.0, 1.0))
        self.assertEqual(plan['texel'], (1 / 1200, 1 / 300))
        self.assertAlmostEqual(plan['spacing'], 30 / 300)
        self.assertEqual(plan['strength'], 4.0)
        self.assertEqual(plan['shade'], ripple.DEFAULTS['shade'])
        self.assertEqual(plan['duration'], ripple.DEFAULTS['duration'])
        self.assertEqual(plan['reach'], ripple.DEFAULTS['reach'])
        # The water begins a shore's width outside the outline, and the far
        # edge is that much nearer for it.
        self.assertAlmostEqual(plan['shore'], ripple.SHORE / 300)
        self.assertAlmostEqual(plan['travel'], (862 - 600 - ripple.SHORE) / 300)
        box = ripple.source(STRIP, AREA, 'bottom', 'bar', 6)
        for key in ('centre', 'half', 'radius'):
            self.assertEqual(plan[key], box[key])

    def test_a_point_source_is_asked_for_in_the_settings(self):
        plan = ripple.plan(STRIP, AREA, 'bottom', {'source': 'point'})
        self.assertEqual(plan['half'], (0.0, 0.0))
        self.assertEqual(plan['radius'], 0.0)

    def test_a_bad_setting_is_an_error_not_a_default(self):
        with self.assertRaises(ValueError):
            ripple.plan(STRIP, AREA, 'bottom', {'spacing': 'wide'})

    def test_a_right_hand_band_measures_in_its_width(self):
        plan = ripple.plan(SIDE_STRIP, SIDE_AREA, 'right')
        self.assertEqual(plan['scale'], (1.0, 3.0))
        self.assertEqual(plan['texel'], (1 / 300, 1 / 900))
        self.assertAlmostEqual(plan['travel'], (1162 - 900 - ripple.SHORE) / 300)


class Policy(unittest.TestCase):
    def test_never_draws_with_animations_off(self):
        self.assertFalse(ripple.allowed(animations=False, current='mains'))

    def test_follows_the_shaders_rung_of_the_power_ladder(self):
        for posture in power_source.POSTURES:
            self.assertEqual(ripple.allowed(animations=True, current=posture),
                             power_source.allows(ripple.EFFECT, current=posture))

    def test_runs_unplugged_and_sheds_at_battery_low(self):
        self.assertTrue(power_source.allows(ripple.EFFECT, current='mains'))
        self.assertTrue(power_source.allows(ripple.EFFECT, current='battery'))
        self.assertFalse(power_source.allows(ripple.EFFECT, current='battery-low'))
        self.assertFalse(power_source.allows(ripple.EFFECT, current='battery-critical'))


class Wave(unittest.TestCase):
    # The water above a docked strip, in units of the band's thickness.
    TRAVEL = (862 - 600) / 300

    def test_nothing_is_drawn_at_the_strike_itself(self):
        for distance in (0.0, 0.01, 0.1, 0.5):
            self.assertEqual(ripple.envelope(distance, 0.0, self.TRAVEL), 0.0)
            self.assertEqual(ripple.slope(distance, 0.0, self.TRAVEL), 0.0)

    def test_the_wave_grows_out_of_the_strips_edge(self):
        # Early on, the only disturbed water is a sliver just past the edge:
        # behind the front, and no nearer the strip than the tail.
        age = 0.05
        front = age * self.TRAVEL
        disturbed = [step / 1000 for step in range(1, 1000)
                     if ripple.envelope(step / 1000, age, self.TRAVEL) > 0]
        self.assertTrue(disturbed)
        self.assertLess(max(disturbed), front)
        self.assertGreater(min(disturbed), front * ripple.TAIL - 1e-9)

    def test_water_ahead_of_the_front_and_inside_the_strip_is_still(self):
        age = 0.5
        front = age * self.TRAVEL
        self.assertEqual(ripple.envelope(front, age, self.TRAVEL), 0.0)
        self.assertEqual(ripple.envelope(front + 0.01, age, self.TRAVEL), 0.0)
        self.assertEqual(ripple.envelope(0.0, age, self.TRAVEL), 0.0)
        self.assertEqual(ripple.envelope(-0.05, age, self.TRAVEL), 0.0)

    def test_water_the_wave_has_passed_closes_again(self):
        age = 0.6
        front = age * self.TRAVEL
        self.assertEqual(ripple.envelope(front * ripple.TAIL / 2, age, self.TRAVEL), 0.0)
        self.assertGreater(ripple.envelope(front * (ripple.TAIL + 1) / 2, age, self.TRAVEL), 0.0)

    def test_the_disturbance_follows_the_front(self):
        # One patch of water is most disturbed just after the front has passed
        # it: not at the strike, and not once the wave has moved on.
        distance = 0.4
        ages = [step / 200 for step in range(201)]
        best = max(ages, key=lambda age: ripple.envelope(distance, age, self.TRAVEL))
        arrives = distance / self.TRAVEL
        self.assertGreater(best, arrives)
        self.assertLess(best, arrives / ripple.TAIL)

    def test_fades_with_age(self):
        def peak(age):
            front = age * self.TRAVEL
            tail = front * ripple.TAIL
            return ripple.envelope(tail + (front - tail) * 2 / 3, age, self.TRAVEL)
        self.assertGreater(peak(0.2), peak(0.5))
        self.assertGreater(peak(0.5), peak(0.8))
        self.assertGreater(peak(0.8), 0.0)

    def test_dies_out_before_the_far_edge_of_the_band(self):
        for age in (step / 20 for step in range(21)):
            self.assertEqual(ripple.envelope(self.TRAVEL, age, self.TRAVEL), 0.0)
            self.assertEqual(ripple.envelope(self.TRAVEL + 0.1, age, self.TRAVEL), 0.0)

    def test_is_silent_outside_its_lifetime(self):
        for age in (-0.01, 1.0, 1.01):
            self.assertEqual(ripple.envelope(0.3, age, self.TRAVEL), 0.0)
            self.assertEqual(ripple.slope(0.3, age, self.TRAVEL), 0.0)

    def test_never_exceeds_one(self):
        for age in (step / 50 for step in range(51)):
            for distance in (step / 100 for step in range(101)):
                self.assertLessEqual(ripple.envelope(distance, age, self.TRAVEL), 1.0 + 1e-9)

    def test_reach_scales_how_far_the_front_gets(self):
        age = 0.5
        self.assertGreater(ripple.envelope(0.3, age, self.TRAVEL, reach=1.0), 0.0)
        self.assertEqual(ripple.envelope(0.3, age, self.TRAVEL, reach=0.5), 0.0)

    def test_the_tilt_is_bounded_by_the_disturbance(self):
        for age in (0.1, 0.3, 0.6, 0.9):
            for distance in (step / 100 for step in range(101)):
                self.assertLessEqual(abs(ripple.slope(distance, age, self.TRAVEL)),
                                     ripple.envelope(distance, age, self.TRAVEL) + 1e-12)

    def test_crests_and_troughs_cancel_so_nothing_brightens_overall(self):
        # With the rings much closer than the annulus is wide, the tilt across
        # the whole band sums to nothing: every crest has its trough.
        age = 0.5
        samples = [ripple.slope(step / 4000, age, self.TRAVEL, spacing=0.01)
                   for step in range(4000)]
        peak = max(abs(sample) for sample in samples)
        self.assertGreater(peak, 0.1)
        self.assertLess(abs(sum(samples)) / len(samples), peak * 0.01)

    def _crests(self, age, spacing):
        front = age * self.TRAVEL
        distances = [step / 10000 for step in range(int(front * 10000))]
        values = [ripple.slope(distance, age, self.TRAVEL, spacing=spacing)
                  for distance in distances]
        return [distances[index] for index in range(1, len(values) - 1)
                if values[index] > values[index - 1] and values[index] >= values[index + 1]
                and values[index] > 0.02]

    def test_crests_are_spaced_as_asked(self):
        spacing = 0.05
        crests = self._crests(0.6, spacing)
        self.assertGreaterEqual(len(crests), 2)
        for earlier, later in zip(crests, crests[1:]):
            self.assertAlmostEqual(later - earlier, spacing, delta=spacing * 0.05)

    def test_crests_move_outward_with_the_front(self):
        self.assertGreater(max(self._crests(0.6, 0.05)), max(self._crests(0.4, 0.05)))


class Shader(unittest.TestCase):
    def test_shares_the_waves_shape_with_its_python_twin(self):
        for name, value in (('TAIL', ripple.TAIL), ('CREST', ripple.CREST),
                            ('DECAY', ripple.DECAY), ('MARGIN', ripple.MARGIN)):
            self.assertIn('const float {} = {};'.format(name, repr(float(value))),
                          ripple.FRAGMENT_SHADER)

    def test_every_number_the_plan_carries_has_a_uniform(self):
        for name in ('scale', 'texel', 'centre', 'half_size', 'radius', 'shore', 'travel',
                     'reach', 'spacing', 'strength', 'shade', 'age'):
            self.assertRegex(ripple.FRAGMENT_SHADER, r'uniform (vec2|float) ' + name + ';')

    def test_writes_premultiplied_colour(self):
        # GTK reads the canvas as premultiplied; straight colour at partial
        # coverage came out brighter than the desktop it was meant to match.
        self.assertIn('fragment = vec4(colour.rgb * alpha, alpha);', ripple.FRAGMENT_SHADER)


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
