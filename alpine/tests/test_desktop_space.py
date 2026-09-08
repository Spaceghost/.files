"""Desktop panels reclaim free edges and yield to fixed desktop chrome."""
import importlib.machinery
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import desktop_space


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
        self.assertEqual(desktop_space.search_rectangle(space)['y'], 820)

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


if __name__ == '__main__':
    unittest.main()
