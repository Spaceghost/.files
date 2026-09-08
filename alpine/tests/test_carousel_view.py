"""Coverflow geometry and motion can be checked without a display server."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import carousel_view


class Layout(unittest.TestCase):
    def test_nearby_cards_are_unique_and_wrap_around_the_selection(self):
        cards = carousel_view.card_layout(12, 0, 1440, 900)
        self.assertEqual(len(cards), 7)
        self.assertEqual({card['index'] for card in cards}, {0, 1, 2, 3, 9, 10, 11})
        self.assertEqual(cards[-1]['index'], 0)

    def test_small_candidate_lists_never_duplicate_a_preview(self):
        for count in range(1, 8):
            with self.subTest(count=count):
                cards = carousel_view.card_layout(count, count - 1, 1280, 720)
                self.assertEqual(len(cards), count)
                self.assertEqual(len({card['index'] for card in cards}), count)

    def test_selected_card_faces_forward_and_neighbors_turn_inward(self):
        cards = {card['index']: card for card in carousel_view.card_layout(7, 3, 1440, 900)}
        self.assertEqual(cards[3]['angle'], 0)
        self.assertEqual(cards[3]['depth'], 0)
        self.assertLess(cards[4]['angle'], 0)
        self.assertGreater(cards[2]['angle'], 0)
        self.assertLess(cards[4]['depth'], cards[3]['depth'])
        self.assertLess(cards[4]['scale'], cards[3]['scale'])

    def test_previews_are_letterboxed_without_changing_aspect(self):
        self.assertEqual(carousel_view.letterbox(1600, 900, 400, 400), (0.0, 87.5, 400.0, 225.0))
        self.assertEqual(carousel_view.letterbox(400, 800, 400, 400), (100.0, 0.0, 200.0, 400.0))

    def test_click_uses_the_frontmost_projected_card(self):
        cards = carousel_view.card_layout(7, 3, 1440, 900)
        middle = cards[-1]
        self.assertEqual(carousel_view.hit_card(cards, middle['x'], middle['y']), 3)
        self.assertIsNone(carousel_view.hit_card(cards, 10, 10))

    def test_empty_carousel_is_safe(self):
        self.assertEqual(carousel_view.card_layout(0, 0, 1440, 900), [])
        self.assertIsNone(carousel_view.hit_card([], 0, 0))


class Motion(unittest.TestCase):
    def test_motion_tracks_elapsed_time_at_different_refresh_rates(self):
        results = []
        for rate in (30, 60, 120, 144):
            value, velocity = 0.0, 0.0
            for _ in range(rate):
                value, velocity = carousel_view.spring_step(value, velocity, 1.0, 1 / rate)
            results.append((value, velocity))
        for result in results[1:]:
            self.assertAlmostEqual(result[0], results[0][0], places=10)
            self.assertAlmostEqual(result[1], results[0][1], places=10)
        self.assertAlmostEqual(results[0][0], 1.0, places=5)

    def test_resting_selection_does_not_overshoot_its_destination(self):
        value, velocity, positions = 0.0, 0.0, []
        for _ in range(90):
            value, velocity = carousel_view.spring_step(value, velocity, 1.0, 1 / 120)
            positions.append(value)
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(all(math.isfinite(value) and 0 <= value <= 1 for value in positions))


if __name__ == '__main__':
    unittest.main()
