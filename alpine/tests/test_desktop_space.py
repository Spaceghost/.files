"""Desktop panels reclaim free edges and yield to fixed desktop chrome."""
import importlib.machinery
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import desktop_space

SETTINGS_HOME = tempfile.TemporaryDirectory()


def setUpModule():
    # search_rectangle reads the Scripture bar's clearance setting: never the real one.
    patcher = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': SETTINGS_HOME.name})
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
    unittest.addModuleCleanup(SETTINGS_HOME.cleanup)


def output(surfaces=()):
    return {'name': 'eDP-1', 'rect': {'x': -1440, 'y': 200, 'width': 1440, 'height': 900},
            'layer_shell_surfaces': list(surfaces)}


def surface(name, x, y, width, height, layer='overlay'):
    return {'namespace': name, 'layer': layer,
            'extent': dict(x=x, y=y, width=width, height=height)}


def tree(*, floating=False, fullscreen=0, hidden_fullscreen=0):
    view = {'id': 3, 'type': 'con', 'app_id': 'foot', 'fullscreen_mode': fullscreen,
            'rect': {'x': -1400, 'y': 400, 'width': 600, 'height': 400}}
    workspace = {'id': 2, 'type': 'workspace', 'fullscreen_mode': 1, 'focus': [3],
                 'nodes': [] if floating else [view],
                 'floating_nodes': [view] if floating else []}
    # A fullscreen container is always a view, so it carries an identity; without
    # one nothing is detected at all and both modes read alike.
    hidden = {'id': 4, 'type': 'workspace', 'nodes': [
        {'id': 5, 'type': 'con', 'app_id': 'foot',
         'fullscreen_mode': hidden_fullscreen}]}
    return {'type': 'root', 'nodes': [dict(output(), type='output', focus=[2],
                                          nodes=[workspace, hidden])]}


class DesktopSpaceTests(unittest.TestCase):
    def test_free_edges_reclaim_bottom_and_right_despite_workspace_fullscreen_marker(self):
        space = desktop_space.screen_space(output(), tree(floating=True))
        self.assertEqual((space['bottom'], space['right']), (16, 16))
        # The cards reclaim the free edge; the search bar keeps its clearance.
        self.assertEqual(desktop_space.search_rectangle(space)['y'], 776)

    def test_fixed_bottom_caption_uses_clearance_while_attached_caption_does_not(self):
        caption = surface('oldbook-decoration', 5, 867, 1430, 28)
        self.assertEqual(desktop_space.screen_space(output([caption]), tree())['bottom'], 60)
        caption['layer'] = 'top'
        space = desktop_space.screen_space(output([caption]), tree(floating=True))
        self.assertEqual(space['bottom'], 16)

    def test_right_caption_only_reserves_right_edge(self):
        caption = surface('oldbook-decoration', 1390, 45, 45, 850)
        space = desktop_space.screen_space(output([caption]), tree(floating=True))
        self.assertEqual((space['bottom'], space['right']), (16, 66))

    def test_other_fixed_bottom_surface_and_top_bar_are_respected(self):
        surfaces = [surface('dock', 200, 840, 1040, 60),
                    surface('top', 4, 0, 1432, 40)]
        space = desktop_space.screen_space(output(surfaces), tree(floating=True))
        self.assertEqual(space['bottom'], 76)
        self.assertEqual(space['origin_y'], 40)

    def test_bottom_waybar_does_not_displace_cards_by_an_entire_screen(self):
        bar = surface('top', 4, 860, 1432, 40)
        space = desktop_space.screen_space(output([bar]), tree(floating=True))
        self.assertEqual(space['origin_y'], 0)
        self.assertLess(space['top'], 100)
        self.assertEqual(space['bottom'], 60)

    def test_own_desktop_surfaces_do_not_reserve_themselves(self):
        surfaces = [surface('oldbook-scripture', 340, 845, 760, 39, 'bottom'),
                    surface('conky', 1080, 760, 340, 120, 'background')]
        self.assertEqual(desktop_space.screen_space(output(surfaces), tree(floating=True))['bottom'], 16)

    def test_actual_fullscreen_reserves_bottom_even_for_a_floating_window(self):
        self.assertEqual(desktop_space.screen_space(output(), tree(floating=True, fullscreen=1))['bottom'], 60)

    def test_hidden_local_fullscreen_does_not_reserve_but_global_does(self):
        for mode, bottom in ((1, 16), (2, 60)):
            self.assertEqual(desktop_space.screen_space(output(), tree(floating=True, hidden_fullscreen=mode))['bottom'], bottom)

    def test_tiled_window_reaching_bottom_reserves_but_float_does_not(self):
        for floating, bottom in ((False, 60), (True, 16)):
            snapshot = tree(floating=floating)
            workspace = snapshot['nodes'][0]['nodes'][0]
            view = (workspace['floating_nodes'] or workspace['nodes'])[0]
            view['rect']['height'] = 690
            self.assertEqual(desktop_space.screen_space(output(), snapshot)['bottom'], bottom)

    def test_conky_pairing_stays_stable_when_fullscreen_occupies_the_free_edge(self):
        helper = importlib.machinery.SourceFileLoader(
            'adaptive_conky_test', str(REPO / 'alpine/desktop/.local/bin/oldbook-conky')).load_module()
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / 'image'
            image.write_bytes(b'wallpaper')
            free = desktop_space.conky_space(desktop_space.screen_space(output(), tree(floating=True)))
            occupied = desktop_space.conky_space(desktop_space.screen_space(output(), tree(fullscreen=1)))
            original = helper.pairing_key(image, free, 'spaceghost', [])
            self.assertEqual(original, helper.pairing_key(image, occupied, 'spaceghost', []))
            self.assertEqual(original, helper.pairing_key(image, free, 'spaceghost', []))
            self.assertEqual((free['bottom'], free['right']), (60, 60))

    def test_notification_popups_do_not_shift_the_search_bar(self):
        # swaync maps a full-height popup window on the right whenever any
        # notification shows; it is transient, not a fixed strip.
        popups = surface('swaync-notification-window', 1060, 40, 380, 827, 'top')
        space = desktop_space.screen_space(output([popups]), tree(floating=True))
        self.assertEqual(space['right'], 16)
        self.assertEqual(desktop_space.search_rectangle(space)['x'], 340)
        control_center = surface('swaync-control-center', 1060, 40, 380, 827, 'top')
        space = desktop_space.screen_space(output([control_center]), tree(floating=True))
        self.assertEqual(space['right'], 16)

    def test_the_landing_wave_does_not_lift_the_search_bar(self):
        # The ripple is an overlay over the lower third of the output for
        # under a second: screen-wide, bottom-anchored, exactly the shape of
        # a fixed bar. Jack: "The ripple.py should be ignored by the conky
        # bible bar." Reserving it lifted the bar 316 pixels on one poll and
        # dropped it on the next.
        wave = surface(desktop_space.RIPPLE_NAMESPACE, 0, 600, 1440, 300, 'overlay')
        still = desktop_space.screen_space(output(), tree(floating=True))
        space = desktop_space.screen_space(output([wave]), tree(floating=True))
        self.assertEqual(space, still)
        self.assertEqual(desktop_space.search_rectangle(space),
                         desktop_space.search_rectangle(still))
        # A right-edge strip's wave is a tall band on the right; same answer.
        side = surface(desktop_space.RIPPLE_NAMESPACE, 960, 0, 480, 900, 'overlay')
        self.assertEqual(desktop_space.screen_space(output([side]), tree(floating=True)), still)


class SearchBarPlacementTests(unittest.TestCase):
    """The Scripture bar ignores the window decoration and starts clear of the bottom bars."""

    def bar(self, surfaces=(), snapshot=None):
        space = desktop_space.screen_space(output(surfaces), snapshot or tree(floating=True),
                                           decoration=False)
        return desktop_space.search_rectangle(space)

    def test_the_decoration_never_moves_the_bar_on_any_layer_or_edge(self):
        free = self.bar()
        self.assertEqual(free, {'x': 340, 'y': 776, 'width': 760, 'height': 64})
        for decoration in (surface('oldbook-decoration', 5, 867, 1430, 28, 'overlay'),
                           surface('oldbook-decoration', 169, 768, 1096, 56, 'top'),
                           surface('oldbook-decoration', 1390, 45, 45, 850, 'overlay'),
                           surface('oldbook-decoration-band', 0, 861, 1440, 39, 'bottom'),
                           surface('oldbook-decoration-band', 1401, 0, 39, 900, 'background')):
            self.assertEqual(self.bar([decoration]), free, decoration)

    def test_it_starts_above_the_bottom_bars_and_windows_never_move_it(self):
        tiled = tree()
        tiled['nodes'][0]['nodes'][0]['nodes'][0]['rect']['height'] = 690
        for snapshot in (tree(floating=True), tiled, tree(floating=True, fullscreen=1),
                         tree(floating=True, hidden_fullscreen=2)):
            rectangle = self.bar(snapshot=snapshot)
            self.assertEqual(rectangle['y'] + rectangle['height'],
                             900 - desktop_space.CAPTION_CLEARANCE)

    def test_a_real_fixed_bottom_bar_still_lifts_it(self):
        self.assertEqual(self.bar([surface('dock', 200, 820, 1040, 80)])['y'], 900 - 96 - 64)

    def test_the_clearance_is_a_setting_with_a_safe_default(self):
        settings = Path(os.environ['XDG_CONFIG_HOME']) / 'oldbook/scripture-bar.json'
        settings.parent.mkdir(exist_ok=True)
        self.addCleanup(settings.unlink, missing_ok=True)
        settings.write_text('{"bottom_clearance": 90}')
        self.assertEqual(self.bar()['y'], 900 - 90 - 64)
        for broken in ('{"bottom_clearance": true}', '{"bottom_clearance": -4}',
                       '{"bottom_clearance": 9000}', '{"bottom_clearance": "90"}', '[90]', 'not json'):
            settings.write_text(broken)
            self.assertEqual(self.bar()['y'], 776, broken)

    def test_the_card_planner_reserves_the_bottom_edge_the_bar_sits_on(self):
        planned = desktop_space.search_rectangle(desktop_space.conky_space(
            desktop_space.screen_space(output(), tree(floating=True))))
        placed = self.bar()
        self.assertEqual(planned['y'] + planned['height'], placed['y'] + placed['height'])

    def test_the_bar_reads_the_screen_without_the_decoration(self):
        source = (REPO / 'alpine/desktop/.local/bin/oldbook-scripture-bar').read_text()
        self.assertIn('read_screen(decoration=False)', source)
        self.assertIn('search_bottom(screen, clearance)', source)


def region_tree(*, current='1', fullscreen=0, tiled=False):
    """An output whose visible workspace carries one window."""
    view = {'id': 3, 'type': 'con' if tiled else 'floating_con', 'app_id': 'foot',
            'fullscreen_mode': fullscreen,
            'rect': {'x': -1240, 'y': 400, 'width': 400, 'height': 200}}
    visible = {'id': 2, 'type': 'workspace', 'name': '1', 'fullscreen_mode': 1, 'focus': [3],
               'nodes': [view] if tiled else [], 'floating_nodes': [] if tiled else [view]}
    hidden = {'id': 4, 'type': 'workspace', 'name': '2', 'fullscreen_mode': 1, 'nodes': [
        {'id': 5, 'type': 'con', 'app_id': 'firefox', 'fullscreen_mode': 0,
         'rect': {'x': -1440, 'y': 200, 'width': 1440, 'height': 900}}]}
    node = dict(output(), type='output', focus=[2], current_workspace=current,
                nodes=[visible, hidden])
    return {'type': 'root', 'nodes': [node]}


class FreeRegionTests(unittest.TestCase):
    """What a BOTTOM-layer surface may draw on, published for plank 0."""

    def cells(self, region):
        return {(column, row) for row, line in enumerate(region['grid'])
                for column, mark in enumerate(line) if mark == '#'}

    def test_every_conky_panel_is_occupied_so_a_bottom_surface_cannot_cover_a_card(self):
        # The single correctness detail of the whole plank: Conky is one
        # surface per panel on BACKGROUND, one layer below BOTTOM.
        panels = [surface('conky', 20, 520, 360, 120, 'background'),
                  surface('conky', 1100, 300, 280, 80, 'background')]
        region = desktop_space.free_region(output(panels), region_tree())
        names = [item['name'] for item in region['occupied'] if item['kind'] == 'layer']
        self.assertEqual(names.count('conky'), 2)
        # 1440x900 on a 72x45 grid is exactly 20x20 logical pixels per cell.
        self.assertIn((1, 26), self.cells(region))
        self.assertIn((55, 15), self.cells(region))

    def test_the_painting_and_the_invisible_band_are_not_occupiers(self):
        # A BOTTOM surface is meant to draw over the painting, and the caption
        # band paints nothing at all; reserving either would leave no region.
        surfaces = [surface('wallpaper', 0, 0, 1440, 900, 'background'),
                    surface('oldbook-background', 0, 0, 1440, 900, 'background'),
                    surface('oldbook-decoration-band', 0, 899, 1440, 1, 'background')]
        region = desktop_space.free_region(output(surfaces), region_tree())
        self.assertEqual([item for item in region['occupied'] if item['kind'] == 'layer'], [])
        self.assertEqual(region['free_cells'], 72 * 45 - 20 * 10)

    def test_the_backdrop_never_moves_a_reading_card(self):
        # CONKY-READING: the cards must not reflow for the backdrop, whatever
        # shape it takes. Skipping it by name is what makes that true rather
        # than merely true of a full-output surface at the origin.
        for extent in ((0, 0, 1440, 900), (0, 840, 1440, 60), (1380, 0, 60, 900)):
            own = surface(desktop_space.EFFECT_NAMESPACE, *extent, 'bottom')
            space = desktop_space.screen_space(output([own]), region_tree())
            self.assertEqual((space['bottom'], space['right'], space['origin_y']),
                             (16, 16, 0))

    def test_the_effect_never_reserves_itself(self):
        own = surface(desktop_space.EFFECT_NAMESPACE, 0, 0, 1440, 900, 'bottom')
        region = desktop_space.free_region(output([own]), region_tree())
        self.assertEqual([item for item in region['occupied'] if item['kind'] == 'layer'], [])

    def test_the_transparent_notification_host_is_not_a_permanent_strip(self):
        # NOTIFICATION-PLACEMENT keeps the empty host transparent; reserving it
        # would carve a third of the output out of the region for nothing.
        host = surface('swaync-notification-window', 1060, 46, 380, 815, 'top')
        region = desktop_space.free_region(output([host]), region_tree())
        self.assertEqual([item for item in region['occupied'] if item['kind'] == 'layer'], [])

    def test_the_landing_wave_is_not_an_occupier(self):
        # It shows a photograph of exactly what is under it, so an effect
        # drawing there is what it shows; carving the band out would clear a
        # third of the output for the length of a wave and paint it back.
        wave = surface(desktop_space.RIPPLE_NAMESPACE, 0, 600, 1440, 300, 'overlay')
        region = desktop_space.free_region(output([wave]), region_tree())
        self.assertEqual([item for item in region['occupied'] if item['kind'] == 'layer'], [])

    def test_the_bar_and_the_caption_are_occupied(self):
        surfaces = [surface('top', 10, 6, 1420, 40, 'overlay'),
                    surface('oldbook-decoration', 84, 781, 1268, 56, 'top'),
                    surface('oldbook-scripture', 340, 843, 760, 41, 'bottom')]
        region = desktop_space.free_region(output(surfaces), region_tree())
        self.assertEqual(sorted(item['name'] for item in region['occupied']
                                if item['kind'] == 'layer'),
                         ['oldbook-decoration', 'oldbook-scripture', 'top'])

    def test_window_rectangles_are_output_local_for_tiled_and_floating_alike(self):
        for tiled in (False, True):
            region = desktop_space.free_region(output(), region_tree(tiled=tiled))
            windows = [item for item in region['occupied'] if item['kind'] == 'window']
            self.assertEqual(windows, [{'x': 200, 'y': 200, 'width': 400, 'height': 200,
                                        'kind': 'window', 'name': 'foot'}])

    def test_a_hidden_workspace_contributes_nothing(self):
        region = desktop_space.free_region(output(), region_tree())
        self.assertEqual([item['name'] for item in region['occupied']], ['foot'])

    def test_fullscreen_is_a_state_rather_than_a_rectangle(self):
        region = desktop_space.free_region(output(), region_tree(fullscreen=1))
        self.assertTrue(region['fullscreen'])
        self.assertEqual(region['occupied'], [])
        self.assertFalse(desktop_space.free_region(output(), region_tree())['fullscreen'])

    def test_a_partly_covered_cell_counts_as_covered(self):
        grid = desktop_space.occupancy_grid(1440, 900, [
            {'x': 19, 'y': 0, 'width': 2, 'height': 1}])
        self.assertEqual(grid[0][:3], '##.')
        self.assertEqual(len(grid), 45)
        self.assertTrue(all(len(row) == 72 for row in grid))

    def test_rectangles_outside_the_output_clamp_instead_of_wrapping(self):
        grid = desktop_space.occupancy_grid(1440, 900, [
            {'x': -400, 'y': -400, 'width': 500, 'height': 500},
            {'x': 1430, 'y': 890, 'width': 4000, 'height': 4000}])
        self.assertEqual(grid[0][:6], '#####.')
        self.assertEqual(grid[-1][-1], '#')
        self.assertEqual(grid[10][40], '.')


class SpaceServiceTests(unittest.TestCase):
    """Publishing and the claim that keeps the service alive."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.runtime = self.directory.name
        self.addCleanup(self.directory.cleanup)

    def test_a_published_record_is_read_back_without_the_compositor(self):
        desktop_space.publish({'version': 1, 'regions': []}, self.runtime)
        self.assertEqual(desktop_space.published(self.runtime),
                         {'version': 1, 'regions': []})
        self.assertTrue(desktop_space.state_path(self.runtime).is_file())

    def test_retracting_leaves_nothing_for_a_consumer_to_read(self):
        desktop_space.publish({'version': 1, 'regions': []}, self.runtime)
        desktop_space.retract(self.runtime)
        self.assertFalse(desktop_space.state_path(self.runtime).exists())
        desktop_space.retract(self.runtime)

    def test_a_held_claim_is_live_and_a_released_one_is_swept(self):
        self.assertEqual(desktop_space.subscribers(self.runtime), [])
        with desktop_space.Subscription('oldbook-edges', self.runtime) as claim:
            self.assertEqual(desktop_space.subscribers(self.runtime), [claim.path.name])
        self.assertEqual(desktop_space.subscribers(self.runtime), [])
        self.assertFalse(claim.path.exists())

    def test_a_claim_name_may_not_escape_its_directory(self):
        for name in ('../elsewhere', '.hidden', ''):
            with self.assertRaises(ValueError):
                desktop_space.Subscription(name, self.runtime)


if __name__ == '__main__':
    unittest.main()
