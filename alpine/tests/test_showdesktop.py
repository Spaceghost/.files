"""Card selection, exit geometry and animation timing for the show-desktop swipe."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/mbp_intel'))
import showdesktop


def view(identifier, x, y, width, height, **extra):
    node = {'id': identifier, 'type': 'con', 'app_id': f'app{identifier}',
            'rect': {'x': x, 'y': y, 'width': width, 'height': height}}
    node.update(extra)
    return node


def workspace(nodes, floating=None, **extra):
    node = {'type': 'workspace', 'name': '1', 'num': 1, 'nodes': nodes,
            'floating_nodes': floating or [], 'rect': OUTPUT}
    node.update(extra)
    return node


OUTPUT = {'x': 0, 'y': 0, 'width': 1440, 'height': 900}


class ParsePpm(unittest.TestCase):
    def test_reads_dimensions_and_pixel_offset(self):
        data = b'P6\n4 2\n255\n' + b'\x00' * 24
        self.assertEqual(showdesktop.parse_ppm(data), (4, 2, 11))

    def test_skips_comments_and_extra_whitespace(self):
        data = b'P6\n# grim\n4  2\n255\n' + b'\x00' * 24
        width, height, offset = showdesktop.parse_ppm(data)
        self.assertEqual((width, height), (4, 2))
        self.assertEqual(len(data) - offset, 24)

    def test_rejects_foreign_format(self):
        with self.assertRaises(ValueError):
            showdesktop.parse_ppm(b'P3\n4 2\n255\n' + b'\x00' * 24)

    def test_rejects_truncated_pixels(self):
        with self.assertRaises(ValueError):
            showdesktop.parse_ppm(b'P6\n4 2\n255\n' + b'\x00' * 23)


class Cards(unittest.TestCase):
    def test_uses_output_local_coordinates(self):
        bounds = {'x': 1440, 'y': 0, 'width': 1440, 'height': 900}
        cards = showdesktop.cards_for(workspace([view(1, 1460, 30, 400, 300)]), bounds)
        self.assertEqual(cards, [{'x': 20, 'y': 30, 'width': 400, 'height': 300}])

    def test_skips_sticky_windows_that_survive_the_swap(self):
        nodes = [view(1, 0, 0, 700, 900), view(2, 700, 0, 740, 900, sticky=True)]
        cards = showdesktop.cards_for(workspace(nodes), OUTPUT)
        self.assertEqual([card['width'] for card in cards], [700])

    def test_clips_windows_hanging_off_the_output(self):
        cards = showdesktop.cards_for(workspace([view(1, -100, 0, 400, 300)]), OUTPUT)
        self.assertEqual(cards, [{'x': 0, 'y': 0, 'width': 300, 'height': 300}])

    def test_drops_windows_entirely_off_the_output(self):
        self.assertEqual(showdesktop.cards_for(workspace([view(1, 2000, 0, 400, 300)]), OUTPUT), [])

    def test_a_fullscreen_window_hides_the_rest(self):
        covered = view(1, 0, 0, 700, 900)
        front = view(2, 0, 0, 1440, 900, fullscreen_mode=1)
        cards = showdesktop.cards_for(workspace([covered, front]), OUTPUT)
        self.assertEqual(cards, [{'x': 0, 'y': 0, 'width': 1440, 'height': 900}])

    def test_a_tabbed_container_contributes_only_its_visible_tab(self):
        tabs = {'type': 'con', 'layout': 'tabbed', 'focus': [7], 'floating_nodes': [],
                'rect': OUTPUT, 'nodes': [view(6, 0, 0, 1440, 900), view(7, 0, 0, 1440, 900)]}
        cards = showdesktop.cards_for(workspace([tabs]), OUTPUT)
        self.assertEqual(len(cards), 1)

    def test_floating_windows_are_drawn_over_tiled_ones(self):
        tiled = [view(1, 0, 0, 1440, 900)]
        floating = [view(2, 200, 200, 400, 300)]
        cards = showdesktop.cards_for(workspace(tiled, floating), OUTPUT)
        self.assertEqual([card['width'] for card in cards], [1440, 400])


class ExitGeometry(unittest.TestCase):
    def clears(self, card, offset):
        left = card['x'] + offset[0]
        top = card['y'] + offset[1]
        return (left + card['width'] <= 0 or left >= 1440
                or top + card['height'] <= 0 or top >= 900)

    def test_left_half_leaves_by_the_left_edge(self):
        card = {'x': 20, 'y': 300, 'width': 400, 'height': 300}
        offset = showdesktop.exit_vector(card, 1440, 900)
        self.assertLess(offset[0], 0)
        self.assertEqual(offset[1], 0)
        self.assertTrue(self.clears(card, offset))

    def test_right_half_leaves_by_the_right_edge(self):
        card = {'x': 1000, 'y': 300, 'width': 400, 'height': 300}
        offset = showdesktop.exit_vector(card, 1440, 900)
        self.assertGreater(offset[0], 0)
        self.assertTrue(self.clears(card, offset))

    def test_a_wide_band_near_the_top_leaves_upward(self):
        card = {'x': 0, 'y': 0, 'width': 1440, 'height': 120}
        offset = showdesktop.exit_vector(card, 1440, 900)
        self.assertEqual(offset[0], 0)
        self.assertLess(offset[1], 0)
        self.assertTrue(self.clears(card, offset))

    def test_a_wide_band_near_the_bottom_leaves_downward(self):
        card = {'x': 0, 'y': 780, 'width': 1440, 'height': 120}
        offset = showdesktop.exit_vector(card, 1440, 900)
        self.assertGreater(offset[1], 0)
        self.assertTrue(self.clears(card, offset))

    def test_a_fullscreen_card_still_clears(self):
        card = {'x': 0, 'y': 0, 'width': 1440, 'height': 900}
        self.assertTrue(self.clears(card, showdesktop.exit_vector(card, 1440, 900)))


class Cropping(unittest.TestCase):
    def test_logical_rectangles_scale_to_capture_pixels(self):
        card = {'x': 10, 'y': 20, 'width': 100, 'height': 50}
        self.assertEqual(showdesktop.crop_bounds(card, 2.0, 2880, 1800), (20, 40, 200, 100))

    def test_a_card_is_never_cropped_past_the_capture(self):
        card = {'x': 1400, 'y': 880, 'width': 200, 'height': 200}
        left, top, width, height = showdesktop.crop_bounds(card, 2.0, 2880, 1800)
        self.assertLessEqual(left + width, 2880)
        self.assertLessEqual(top + height, 1800)

    def test_rows_are_copied_out_tightly_packed(self):
        # A 4x2 image of distinct bytes; take the right half of both rows.
        data = b'P6\n4 2\n255\n' + bytes(range(24))
        offset = showdesktop.parse_ppm(data)[2]
        pixels = showdesktop.crop_rows(data, offset, 12, (2, 0, 2, 2))
        self.assertEqual(pixels, bytes([6, 7, 8, 9, 10, 11, 18, 19, 20, 21, 22, 23]))

    def test_a_full_frame_crop_returns_every_pixel(self):
        data = b'P6\n4 2\n255\n' + bytes(range(24))
        offset = showdesktop.parse_ppm(data)[2]
        self.assertEqual(showdesktop.crop_rows(data, offset, 12, (0, 0, 4, 2)), bytes(range(24)))


class Timing(unittest.TestCase):
    def test_easing_curves_span_the_unit_interval(self):
        for curve in (showdesktop.EXIT_CURVE, showdesktop.RETURN_CURVE):
            self.assertAlmostEqual(showdesktop.bezier(*curve, 0), 0, places=4)
            self.assertAlmostEqual(showdesktop.bezier(*curve, 1), 1, places=4)

    def test_easing_is_monotonic(self):
        for curve in (showdesktop.EXIT_CURVE, showdesktop.RETURN_CURVE):
            values = [showdesktop.bezier(*curve, i / 40) for i in range(41)]
            self.assertEqual(values, sorted(values))

    def test_leaving_accelerates_and_arriving_decelerates(self):
        # Half way through, an exit has covered less than half its path and a
        # return has covered more; that asymmetry is the point of the curves.
        self.assertLess(showdesktop.bezier(*showdesktop.EXIT_CURVE, 0.5), 0.45)
        self.assertGreater(showdesktop.bezier(*showdesktop.RETURN_CURVE, 0.5), 0.55)

    def test_stagger_is_capped_so_crowded_workspaces_stay_quick(self):
        self.assertEqual(showdesktop.stagger_step(1), 0)
        self.assertEqual(showdesktop.stagger_step(3), showdesktop.STAGGER_MS)
        self.assertLessEqual(showdesktop.sequence_ms(12, showdesktop.OUT_MS),
                             showdesktop.OUT_MS + showdesktop.STAGGER_BUDGET_MS)

    def test_top_left_card_launches_first(self):
        cards = [{'x': 700, 'y': 400, 'width': 10, 'height': 10},
                 {'x': 0, 'y': 0, 'width': 10, 'height': 10},
                 {'x': 700, 'y': 0, 'width': 10, 'height': 10}]
        self.assertEqual(showdesktop.stagger_order(cards), [2, 0, 1])

    def test_showing_runs_from_rest_to_clear(self):
        self.assertEqual(showdesktop.travel_at(0, 2, 0, showdesktop.OUT_MS, False), 0)
        self.assertEqual(showdesktop.travel_at(0, 2, showdesktop.OUT_MS,
                                               showdesktop.OUT_MS, False), 1)

    def test_restoring_runs_from_clear_to_rest(self):
        self.assertEqual(showdesktop.travel_at(0, 2, 0, showdesktop.IN_MS, True), 1)
        self.assertEqual(showdesktop.travel_at(0, 2, showdesktop.IN_MS,
                                               showdesktop.IN_MS, True), 0)

    def test_a_later_slot_is_still_at_rest_when_the_first_has_moved(self):
        step = showdesktop.stagger_step(3)
        self.assertGreater(showdesktop.travel_at(0, 3, step, showdesktop.OUT_MS, False), 0)
        self.assertEqual(showdesktop.travel_at(2, 3, step, showdesktop.OUT_MS, False), 0)

    def test_every_card_has_landed_by_the_end_of_the_sequence(self):
        total = showdesktop.sequence_ms(4, showdesktop.IN_MS)
        for slot in range(4):
            self.assertEqual(showdesktop.travel_at(slot, 4, total, showdesktop.IN_MS, True), 0)


class Switching(unittest.TestCase):
    def test_a_numbered_workspace_is_addressed_by_number(self):
        self.assertEqual(showdesktop.switch_command({'name': '3: LAB · vim', 'num': 3}),
                         'workspace number "3: Lab"')

    def test_a_named_workspace_falls_back_to_back_and_forth(self):
        # Live renaming makes the captured name an unreliable address.
        self.assertEqual(showdesktop.switch_command({'name': 'scratch', 'num': -1}),
                         'workspace back_and_forth')


if __name__ == '__main__':
    unittest.main()
