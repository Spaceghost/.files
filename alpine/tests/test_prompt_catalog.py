"""Scene and insertion selection must never repeat a painting while fresh pairs remain."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/wallpapers'))
import prompt_catalog


def catalog(scenes=('a', 'b'), insertions=('x', 'y'), mediums=None, **extra):
    document = {'style': 'Shared style.',
                'scenes': [{'id': i, 'title': i.upper(), 'description': 'Scene ' + i} for i in scenes]}
    if insertions is not None:
        document['insertions'] = [{'id': i, 'title': i.upper(), 'description': 'Insertion ' + i}
                                  for i in insertions]
    if mediums is not None:
        document['mediums'] = [{'id': i, 'title': i.upper(), 'description': 'Medium ' + i}
                               for i in mediums]
    document.update(extra)
    return document


class ValidationTests(unittest.TestCase):
    def test_accepts_a_catalog_without_the_newer_banks(self):
        legacy = {'style': 'Old.', 'scenes': [{'id': 'one', 'title': 'One', 'description': 'D'}]}
        self.assertIs(prompt_catalog.validate(legacy), legacy)

    def test_rejects_duplicate_and_malformed_identifiers(self):
        for scenes in (('a', 'a'), ('A',), ('-bad',)):
            with self.assertRaises(ValueError):
                prompt_catalog.validate(catalog(scenes=scenes))

    def test_rejects_an_unknown_selection_mode(self):
        with self.assertRaises(ValueError):
            prompt_catalog.validate(catalog(scene_selection='sometimes'))

    def test_rejects_turning_every_scene_off(self):
        document = catalog()
        for scene in document['scenes']:
            scene['enabled'] = False
        with self.assertRaises(ValueError):
            prompt_catalog.validate(document)

    def test_live_catalog_validates_and_offers_many_combinations(self):
        document = prompt_catalog.load_catalog(REPO / 'alpine/wallpapers/prompts.json')
        scenes = prompt_catalog.enabled(document, 'scenes')
        insertions = len(prompt_catalog.enabled(document, 'insertions'))
        mediums = len(prompt_catalog.enabled(document, 'mediums'))
        fixed = sum(1 for scene in scenes if scene.get('fixed_medium'))
        total = fixed * insertions + (len(scenes) - fixed) * insertions * mediums
        self.assertGreater(total, 2000)

    def test_live_style_forbids_treating_sacred_subjects_as_a_joke(self):
        document = prompt_catalog.load_catalog(REPO / 'alpine/wallpapers/prompts.json')
        style = document['style'].lower()
        for rule in ('never give them a halo', 'never parody scripture',
                     'object of veneration', 'never depict space ghost'):
            self.assertIn(rule, style, rule)

    def test_no_insertion_style_places_space_ghost_in_a_sacred_role(self):
        """Guard the exact phrasings that once cast Space Ghost as a holy figure."""
        document = prompt_catalog.load_catalog(REPO / 'alpine/wallpapers/prompts.json')
        violations = ('haloed and solemn', 'devotional seriousness', 'reverent medieval glazing',
                      'in the pose of a renaissance donor portrait', 'smaller than the sacred figures',
                      'holding his power bands like attributes')
        for insertion in prompt_catalog.bank(document, 'insertions'):
            text = insertion['description'].lower()
            for phrase in violations:
                self.assertNotIn(phrase, text, f"{insertion['id']}: {phrase}")

    def test_reworked_insertions_state_their_secular_limit(self):
        document = prompt_catalog.load_catalog(REPO / 'alpine/wallpapers/prompts.json')
        by_id = {item['id']: item['description'].lower()
                 for item in prompt_catalog.bank(document, 'insertions')}
        for identifier in ('stained-glass', 'donor-portrait', 'statue', 'illuminated-marginalia'):
            self.assertIn(identifier, by_id)
            limit = by_id[identifier]
            self.assertTrue('never' in limit or 'no sacred' in limit,
                            f'{identifier} must say where it may not appear')


class EnabledTests(unittest.TestCase):
    def test_disabled_entries_are_skipped(self):
        document = catalog()
        document['scenes'][0]['enabled'] = False
        self.assertEqual([s['id'] for s in prompt_catalog.enabled(document, 'scenes')], ['b'])

    def test_a_fully_disabled_bank_falls_back_rather_than_painting_nothing(self):
        document = catalog()
        for insertion in document['insertions']:
            insertion['enabled'] = False
        self.assertEqual(len(prompt_catalog.enabled(document, 'insertions')), 2)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='oldbook-history-test-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'history.json'

    def test_round_trips_recorded_pairs(self):
        history = prompt_catalog.PaintHistory(self.path)
        history.record('a', 'x', 'm', seed='seed')
        history.save()
        self.assertEqual(prompt_catalog.PaintHistory.load(self.path).used(), {('a', 'x', 'm')})

    def test_damaged_history_falls_back_to_the_bootstrap(self):
        self.path.write_text('{ not json')
        history = prompt_catalog.PaintHistory.load(self.path, [{'scene': 'a', 'insertion': None}])
        self.assertEqual(history.used(), {('a', None, None)})


class SelectionTests(unittest.TestCase):
    def history(self, pairs=()):
        history = prompt_catalog.PaintHistory(Path('unused'))
        for entry in pairs:
            history.record(*entry)
        return history

    def test_explicit_identifiers_win_over_the_bank(self):
        scene, insertion, medium = prompt_catalog.choose(
            catalog(mediums=('m',)), self.history(),
            scene_id='b', insertion_id='x', medium_id='m')
        self.assertEqual((scene['id'], insertion['id'], medium['id']), ('b', 'x', 'm'))

    def test_unknown_identifier_is_rejected(self):
        with self.assertRaises(RuntimeError):
            prompt_catalog.choose(catalog(), self.history(), scene_id='nope')

    def test_a_painted_pair_is_avoided_while_fresh_pairs_remain(self):
        document = catalog(scenes=('a',), insertions=('x', 'y'))
        scene, insertion, _medium = prompt_catalog.choose(
            document, self.history([('a', 'x', None)]))
        self.assertEqual((scene['id'], insertion['id']), ('a', 'y'))

    def test_shuffle_exhausts_every_pair_before_any_repeat(self):
        document = catalog(scenes=('a', 'b', 'c'), insertions=('x', 'y'))
        history = self.history()
        seen = []
        for _ in range(6):
            scene, insertion, _medium = prompt_catalog.choose(document, history)
            history.record(scene['id'], insertion['id'])
            seen.append((scene['id'], insertion['id']))
        self.assertEqual(len(set(seen)), 6, 'shuffle repeated a pair before exhausting the bank')

    def test_rotate_advances_from_the_last_painted_scene(self):
        document = catalog(scenes=('a', 'b', 'c'), insertions=('x',),
                           scene_selection='rotate', insertion_selection='rotate')
        scene, _insertion, _medium = prompt_catalog.choose(
            document, self.history([('a', 'x', None)]))
        self.assertEqual(scene['id'], 'b')

    def test_an_exhausted_bank_returns_the_least_recently_painted_pair(self):
        document = catalog(scenes=('a',), insertions=('x', 'y'))
        history = self.history([('a', 'x', None), ('a', 'y', None), ('a', 'y', None)])
        scene, insertion, _medium = prompt_catalog.choose(document, history)
        self.assertEqual((scene['id'], insertion['id']), ('a', 'x'))

    def test_a_catalog_without_insertions_still_selects_a_scene(self):
        scene, insertion, medium = prompt_catalog.choose(
            catalog(insertions=None), self.history())
        self.assertIsNone(insertion)
        self.assertIsNone(medium)
        self.assertIn(scene['id'], ('a', 'b'))

    def test_a_scene_that_fixes_its_medium_is_never_paired_with_one(self):
        document = catalog(scenes=('a',), insertions=('x',), mediums=('m', 'n'))
        document['scenes'][0]['fixed_medium'] = True
        combinations = set()
        history = self.history()
        for _ in range(4):
            scene, insertion, medium = prompt_catalog.choose(document, history)
            history.record(scene['id'], insertion['id'], medium['id'] if medium else None)
            combinations.add((scene['id'], insertion['id'], medium['id'] if medium else None))
        self.assertEqual(combinations, {('a', 'x', None)})

    def test_a_free_scene_visits_every_medium_before_repeating(self):
        document = catalog(scenes=('a',), insertions=('x',), mediums=('m', 'n', 'o'))
        history = self.history()
        seen = []
        for _ in range(3):
            scene, insertion, medium = prompt_catalog.choose(document, history)
            history.record(scene['id'], insertion['id'], medium['id'])
            seen.append(medium['id'])
        self.assertEqual(sorted(seen), ['m', 'n', 'o'])


class ComposeTests(unittest.TestCase):
    def test_prompt_carries_style_theme_scene_insertion_and_seed(self):
        document = catalog()
        theme = {'name': 'Gruvbox', 'image_style': 'Warm charcoal.'}
        document['mediums'] = [{'id': 'm', 'title': 'M', 'description': 'Medium m'}]
        prompt = prompt_catalog.compose_prompt(
            document, theme, document['scenes'][0], document['insertions'][0],
            document['mediums'][0], 'abc123')
        for fragment in ('Shared style.', 'Warm charcoal.', 'Scene a', 'Insertion x',
                         'Medium m', 'abc123'):
            self.assertIn(fragment, prompt)

    def test_unthemed_prompt_omits_the_theme_paragraph(self):
        document = catalog()
        prompt = prompt_catalog.compose_prompt(
            document, {'name': 'Unthemed', 'image_style': ''},
            document['scenes'][0], None, None, 'seed')
        self.assertNotIn('Theme:', prompt)
        self.assertNotIn('insertion style:', prompt)
        self.assertNotIn('Medium and treatment:', prompt)

    def test_each_seed_is_distinct(self):
        self.assertNotEqual(prompt_catalog.variation_seed(), prompt_catalog.variation_seed())


if __name__ == '__main__':
    unittest.main()
