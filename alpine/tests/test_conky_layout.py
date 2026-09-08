"""Desktop panels must stay transparent, legible and clear of the painting's subject."""
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import conky_layout

LIVE_PANELS = REPO / 'alpine/desktop/.config/conky/panels.json'
AREA = {'width': 1440, 'height': 900, 'top': 44, 'bottom': 16, 'left': 16, 'right': 16}


def grid(columns=20, rows=10, busy=range(8, 13), brightness=0.2):
    """A grid whose busy columns stand in for the painted subject."""
    return {
        'columns': columns, 'rows': rows,
        'detail': [[1.0 if column in busy else 0.0 for column in range(columns)]
                   for _ in range(rows)],
        'brightness': [[brightness] * columns for _ in range(rows)],
        'colour': [[[30, 28, 24]] * columns for _ in range(rows)],
    }


class ColourTests(unittest.TestCase):
    def test_parses_and_formats_colours(self):
        self.assertEqual(conky_layout.parse_colour('#EBDBB2'), (235, 219, 178))
        self.assertEqual(conky_layout.format_colour((235, 219, 178)), '#ebdbb2')

    def test_rejects_a_colour_that_is_not_six_hex_digits(self):
        with self.assertRaises(ValueError):
            conky_layout.parse_colour('not-a-colour')

    def test_contrast_ratio_spans_black_to_white(self):
        self.assertAlmostEqual(conky_layout.contrast_ratio((255, 255, 255), (0, 0, 0)), 21.0, places=1)

    def test_readable_lifts_a_dim_colour_off_a_dark_region(self):
        adjusted = conky_layout.readable('#3c3836', (16, 14, 12))
        self.assertGreaterEqual(conky_layout.contrast_ratio(adjusted, (16, 14, 12)),
                                conky_layout.MIN_CONTRAST)

    def test_readable_darkens_a_pale_colour_on_a_bright_region(self):
        adjusted = conky_layout.readable('#fbf1c7', (240, 236, 228))
        self.assertGreaterEqual(conky_layout.contrast_ratio(adjusted, (240, 236, 228)),
                                conky_layout.MIN_CONTRAST)

    def test_palette_keeps_supplied_colours_and_derives_the_missing_series(self):
        palette = conky_layout.resolve_palette(
            {'palette': {'background': '#11161B', 'foreground': '#E7E1D5', 'accent': '#D8755B'}})
        self.assertEqual(palette['foreground'], '#e7e1d5')
        for key in conky_layout.SERIES_KEYS:
            self.assertRegex(palette[key], r'^#[0-9a-f]{6}$')

    def test_a_theme_without_a_palette_still_resolves(self):
        palette = conky_layout.resolve_palette({'id': 'none', 'name': 'Unthemed'})
        self.assertEqual(palette['accent'], conky_layout.FALLBACK_PALETTE['accent'])


class PlacementTests(unittest.TestCase):
    def panel(self, identifier='one', width=144, height=180, **extra):
        return dict({'id': identifier, 'width': width, 'height': height,
                     'text': 'body'}, **extra)

    def test_panel_avoids_the_busy_centre_of_the_painting(self):
        placement = conky_layout.place_panels([self.panel()], grid(), AREA)[0]
        cell = placement['cell']
        occupied = set(range(cell['left'], cell['left'] + cell['columns']))
        self.assertFalse(occupied & set(range(8, 13)),
                         'panel was placed over the busiest part of the wallpaper')

    def test_placement_respects_the_bar_and_edge_insets(self):
        placement = conky_layout.place_panels([self.panel()], grid(), AREA)[0]
        self.assertGreaterEqual(placement['y'], AREA['top'] - 1)
        self.assertGreaterEqual(placement['x'], 0)
        self.assertLessEqual(placement['x'] + placement['width'], AREA['width'] - AREA['right'] + 1)
        self.assertLessEqual(placement['y'] + placement['height'], AREA['height'] - AREA['bottom'] + 1)

    def test_panels_never_overlap_each_other(self):
        panels = [self.panel(f'p{index}') for index in range(4)]
        placements = conky_layout.place_panels(panels, grid(), AREA)
        self.assertEqual(len(placements), 4)
        for first in range(len(placements)):
            for second in range(first + 1, len(placements)):
                one, two = placements[first], placements[second]
                separate = (one['x'] + one['width'] <= two['x'] or two['x'] + two['width'] <= one['x']
                            or one['y'] + one['height'] <= two['y']
                            or two['y'] + two['height'] <= one['y'])
                self.assertTrue(separate, f'{one["id"]} overlaps {two["id"]}')

    def test_a_panel_too_large_for_the_area_is_dropped_rather_than_misplaced(self):
        placements = conky_layout.place_panels(
            [self.panel(width=4000, height=4000)], grid(), AREA)
        self.assertEqual(placements, [])

    def test_higher_priority_panels_choose_first(self):
        panels = [self.panel('low', priority=1), self.panel('high', priority=99)]
        placements = conky_layout.place_panels(panels, grid(), AREA)
        self.assertEqual(placements[0]['id'], 'high')

    def test_detail_and_brightness_keep_the_same_ranked_free_regions(self):
        wallpaper = grid(columns=8, rows=6, busy=())
        wallpaper['detail'] = [
            [0.0, 0.1, 0.2, 0.1, 0.5, 0.3, 0.2, 0.0],
            [0.1, 0.1, 0.2, 0.2, 0.8, 0.5, 0.3, 0.1],
            [0.1, 0.0, 0.3, 0.6, 1.0, 0.7, 0.2, 0.1],
            [0.2, 0.1, 0.6, 1.0, 0.9, 0.6, 0.1, 0.0],
            [0.0, 0.1, 0.5, 0.8, 0.7, 0.4, 0.0, 0.1],
            [0.0, 0.0, 0.2, 0.3, 0.4, 0.1, 0.2, 0.0],
        ]
        wallpaper['brightness'] = [[0.2 + (row + column) % 4 / 10
                                    for column in range(8)] for row in range(6)]
        panels = [self.panel('upper', 200, 100, priority=2, prefer='top-right'),
                  self.panel('lower', 200, 200, priority=1, prefer='bottom-right'),
                  self.panel('left', 200, 100, prefer='left')]
        placements = conky_layout.place_panels(
            panels, wallpaper, {'width': 800, 'height': 600})
        self.assertEqual([(panel['id'], panel['x'], panel['y']) for panel in placements],
                         [('upper', 600, 0), ('lower', 600, 400), ('left', 0, 500)])
        for panel, score in zip(placements, (-0.4087, -0.2263, -0.1879)):
            self.assertAlmostEqual(panel['score'], score, places=4)

    def test_bottom_right_preference_seats_a_card_in_the_lower_right(self):
        placement = conky_layout.place_panels(
            [self.panel(prefer='bottom-right')], grid(), AREA)[0]
        self.assertGreaterEqual(placement['x'], AREA['width'] / 2)
        self.assertGreaterEqual(placement['y'], AREA['height'] / 2)

    def test_top_right_preference_leaves_the_lower_right_free(self):
        placement = conky_layout.place_panels(
            [self.panel(prefer='top-right')], grid(), AREA)[0]
        self.assertGreaterEqual(placement['x'], AREA['width'] / 2)
        self.assertLess(placement['y'] + placement['height'], AREA['height'] / 2)

    def test_corner_preference_yields_to_a_busy_right_side(self):
        placement = conky_layout.place_panels(
            [self.panel(prefer='bottom-right')], grid(busy=range(10, 20)), AREA)[0]
        self.assertLessEqual(placement['x'] + placement['width'], AREA['width'] / 2)

    def test_corner_preference_respects_a_reserved_lower_right(self):
        reserved = {'x': 720, 'y': 450, 'width': 720, 'height': 450}
        placement = conky_layout.place_panels(
            [self.panel(prefer='bottom-right')], grid(), AREA, reserved=[reserved])[0]
        self.assertTrue(placement['x'] + placement['width'] <= reserved['x']
                        or placement['y'] + placement['height'] <= reserved['y'])

    def test_cards_sharing_a_corner_preference_keep_their_gap(self):
        panels = [self.panel(f'p{index}', prefer='bottom-right') for index in range(3)]
        placements = conky_layout.place_panels(panels, grid(), AREA)
        self.assertEqual(len(placements), 3)
        for index, one in enumerate(placements):
            self.assertLessEqual(one['x'] + one['width'], 1424)
            self.assertLessEqual(one['y'] + one['height'], 884)
            for two in placements[index + 1:]:
                self.assertTrue(one['x'] + one['width'] + 72 <= two['x']
                                or two['x'] + two['width'] + 72 <= one['x']
                                or one['y'] + one['height'] + 90 <= two['y']
                                or two['y'] + two['height'] + 90 <= one['y'])

    def test_default_slow_text_fills_the_lower_right_beside_the_subject(self):
        document = conky_layout.load_panels(LIVE_PANELS)
        panels = [panel for panel in document['panels'] if panel.get('enabled', True)]
        placements = conky_layout.place_panels(panels, grid(), AREA)
        lower_right_text = [panel for panel in placements
                            if panel['id'] in ('ghost', 'gallery')
                            and panel['x'] >= AREA['width'] / 2
                            and panel['y'] >= AREA['height'] / 2]
        self.assertTrue(lower_right_text, 'the lower-right side has no slow-text card')


class ColoursForRegionTests(unittest.TestCase):
    def test_text_colours_reach_the_contrast_floor_over_a_dark_region(self):
        placement = {'background': [18, 16, 14]}
        colours = conky_layout.panel_colours(
            placement, conky_layout.resolve_palette({'palette': {'foreground': '#282828'}}))
        self.assertGreaterEqual(
            conky_layout.contrast_ratio(conky_layout.parse_colour(colours['default']), (18, 16, 14)),
            conky_layout.MIN_CONTRAST)

    def test_text_colours_adapt_to_a_bright_region(self):
        colours = conky_layout.panel_colours({'background': [242, 240, 235]},
                                             conky_layout.resolve_palette({}))
        self.assertGreaterEqual(
            conky_layout.contrast_ratio(conky_layout.parse_colour(colours['default']),
                                        (242, 240, 235)),
            conky_layout.MIN_CONTRAST)


class ConfigTests(unittest.TestCase):
    def config(self):
        panel = {'id': 'demo', 'width': 200, 'height': 100, 'text': 'HELLO ${cpu}'}
        placement = {'x': 40, 'y': 80, 'width': 200, 'height': 100, 'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        return conky_layout.render_config(panel, placement, colours,
                                          {'font': 'Test:size=9', 'update_interval': 2.0})

    def test_config_is_transparent_and_wayland_native(self):
        text = self.config()
        self.assertIn("own_window_colour = '#00000000'", text)
        self.assertIn('out_to_wayland = true', text)
        self.assertIn('out_to_x = false', text)

    def test_config_pins_the_computed_rectangle_and_body(self):
        text = self.config()
        self.assertIn('gap_x = 40', text)
        self.assertIn('gap_y = 80', text)
        self.assertIn('alignment = \'top_left\'', text)
        self.assertIn('HELLO ${cpu}', text)

    def test_waybar_reservation_does_not_shift_wallpaper_coordinates(self):
        panel = {'id': 'power', 'text': 'Battery'}
        placement = {'x': 1140, 'y': 740, 'width': 280, 'height': 80,
                     'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        config = conky_layout.render_config(panel, placement, colours, {'origin_y': 42})
        margin = int(re.search(r'gap_y = (-?\d+)', config)[1])
        actual_y = 42 + margin
        self.assertEqual(actual_y, placement['y'])
        self.assertLessEqual(actual_y + placement['height'] + 12, 865)

    def test_lua_strings_escape_quotes(self):
        self.assertEqual(conky_layout.lua_string("it's"), r"'it\'s'")

    def test_reading_cards_receive_the_native_mouse_hook(self):
        placement = {'x': 40, 'y': 80, 'width': 360, 'height': 140,
                     'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        for identifier in ('scripture', 'witness', 'ghost', 'gallery'):
            with self.subTest(panel=identifier):
                text = conky_layout.render_config(
                    {'id': identifier, 'text': 'Read me'}, placement, colours,
                    {'click_hook': '/tmp/mbp-intel/conky_click.lua'})
                self.assertIn("lua_load = '/tmp/mbp-intel/conky_click.lua'", text)
                self.assertIn("lua_mouse_hook = 'mbp_intel_click'", text)
                self.assertIn("own_window_type = 'desktop'", text)

    def test_static_cards_do_not_receive_a_mouse_hook(self):
        placement = {'x': 40, 'y': 80, 'width': 360, 'height': 140,
                     'background': [20, 20, 20]}
        colours = conky_layout.panel_colours(placement, conky_layout.resolve_palette({}))
        for identifier in ('masthead', 'power'):
            with self.subTest(panel=identifier):
                text = conky_layout.render_config(
                    {'id': identifier, 'text': 'Static'}, placement, colours,
                    {'click_hook': '/tmp/mbp-intel/conky_click.lua'})
                self.assertNotIn('lua_mouse_hook', text)
                self.assertNotIn('lua_load', text)


class PanelFileTests(unittest.TestCase):
    def write(self, document):
        temp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(document, temp)
        temp.close()
        self.addCleanup(lambda: Path(temp.name).unlink(missing_ok=True))
        return temp.name

    def test_live_panel_file_is_valid(self):
        document = conky_layout.load_panels(LIVE_PANELS)
        self.assertTrue(any(panel.get('enabled', True) for panel in document['panels']))

    def test_rejects_a_panel_without_text_or_size(self):
        for panel in ({'id': 'a', 'width': 10, 'height': 10},
                      {'id': 'a', 'width': 0, 'height': 10, 'text': 'x'},
                      {'id': 'BAD', 'width': 10, 'height': 10, 'text': 'x'}):
            with self.assertRaises(ValueError):
                conky_layout.load_panels(self.write({'panels': [panel]}))

    def test_rejects_duplicate_panel_identifiers(self):
        panel = {'id': 'a', 'width': 10, 'height': 10, 'text': 'x'}
        with self.assertRaises(ValueError):
            conky_layout.load_panels(self.write({'panels': [panel, dict(panel)]}))


class PlanTests(unittest.TestCase):
    def test_plan_produces_one_config_per_placed_panel(self):
        panels = [{'id': 'a', 'width': 144, 'height': 180, 'text': 'A'},
                  {'id': 'b', 'width': 144, 'height': 180, 'text': 'B'}]
        plans = conky_layout.plan(panels, grid(), AREA, conky_layout.resolve_palette({}),
                                  {'font': 'Test:size=9'})
        self.assertEqual({entry['panel']['id'] for entry in plans}, {'a', 'b'})
        for entry in plans:
            self.assertIn('conky.text', entry['config'])


if __name__ == '__main__':
    unittest.main()
