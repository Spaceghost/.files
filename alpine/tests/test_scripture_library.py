"""The offline library must convert sources faithfully and record their licences."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/mbp_intel'))
import scripture
import scripture_library as lib

ASSETS = REPO / 'alpine/assets/scripture'
MANIFEST = ASSETS / 'library.json'


class CleanTests(unittest.TestCase):
    def test_strips_footnote_markup_that_both_sources_ship(self):
        raw = ('When God began<sup class="footnote-marker">a</sup>'
               '<i class="footnote">a note</i> to create')
        self.assertEqual(lib.clean(raw), 'When God began to create')

    def test_unescapes_entities_and_flattens_whitespace(self):
        self.assertEqual(lib.clean('Moses &amp;\n  Aaron\tspoke'), 'Moses & Aaron spoke')


class ConversionTests(unittest.TestCase):
    def getbible(self):
        return {'books': [{'name': 'Genesis', 'chapters': [
            {'chapter': '1', 'verses': [{'verse': '1', 'text': 'In the beginning '},
                                        {'verse': '2', 'text': '  '}]}]}]}

    def test_getbible_rows_drop_empty_verses(self):
        rows = lib.getbible_rows(self.getbible())
        self.assertEqual(rows, [('Genesis', 1, 1, 'In the beginning')])

    def test_getbible_rejects_a_document_without_books(self):
        with self.assertRaises(ValueError):
            lib.getbible_rows({'books': []})

    def test_sefaria_rows_number_chapters_and_verses_in_order(self):
        payload = {'versions': [{'license': 'Public Domain',
                                 'text': [['first', 'second'], ['third']]}]}
        rows, version = lib.sefaria_rows('Genesis', payload)
        self.assertEqual(rows, [('Genesis', 1, 1, 'first'), ('Genesis', 1, 2, 'second'),
                                ('Genesis', 2, 1, 'third')])
        self.assertEqual(version['license'], 'Public Domain')

    def test_sefaria_joins_a_nested_segment(self):
        payload = {'versions': [{'text': [[['a', 'b']]]}]}
        rows, _version = lib.sefaria_rows('Berakhot', payload)
        self.assertEqual(rows, [('Berakhot', 1, 1, 'a b')])

    def test_talmud_sections_are_numbered_by_daf(self):
        payload = {'versions': [{'text': ['', '', ['first line of 2a']]}]}
        rows, _version = lib.sefaria_rows('Berakhot', payload, section_base=0)
        self.assertEqual(rows, [('Berakhot', 2, 1, 'first line of 2a')])

    def test_sefaria_rejects_a_response_with_no_version(self):
        with self.assertRaises(ValueError):
            lib.sefaria_rows('Genesis', {'versions': []})


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mbp-intel-library-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_written_text_round_trips_through_the_reader(self):
        rows = [('Genesis', 1, 1, 'In the beginning'), ('Genesis', 1, 2, 'And the earth')]
        digest, count = lib.write_text(rows, self.root / 'demo.tsv.gz')
        self.assertEqual(count, 2)
        self.assertEqual(len(digest), 64)
        with gzip.open(self.root / 'demo.tsv.gz', 'rt') as handle:
            self.assertEqual(handle.read().splitlines()[0],
                             'Genesis\t1\t1\tIn the beginning')

    def test_the_same_rows_always_produce_the_same_bytes(self):
        rows = [('Genesis', 1, 1, 'In the beginning')]
        first, _ = lib.write_text(rows, self.root / 'a.tsv.gz')
        second, _ = lib.write_text(rows, self.root / 'b.tsv.gz')
        self.assertEqual(first, second)

    def test_refuses_a_record_containing_a_tab(self):
        with self.assertRaises(ValueError):
            lib.write_text([('Genesis', 1, 1, 'a\tb')], self.root / 'bad.tsv.gz')

    def test_refuses_to_write_nothing(self):
        with self.assertRaises(ValueError):
            lib.write_text([], self.root / 'empty.tsv.gz')

    def test_installed_texts_needs_both_the_data_and_its_record(self):
        lib.write_text([('Genesis', 1, 1, 'x')], self.root / 'demo.tsv.gz')
        self.assertEqual(lib.installed_texts(self.root), {})
        (self.root / 'demo.json').write_text(json.dumps({'id': 'demo', 'verses': 1}))
        self.assertIn('demo', lib.installed_texts(self.root))


class ManifestTests(unittest.TestCase):
    def test_live_manifest_is_valid_and_states_every_licence(self):
        document = lib.load_manifest(MANIFEST)
        for text in document['texts']:
            self.assertTrue(text['license'].strip(), text['id'])
        identifiers = {text['id'] for text in document['texts']}
        for expected in ('kjv', 'asv', 'web', 'ylt', 'douay-rheims',
                         'tanakh-jps1917', 'tanakh-hebrew', 'talmud-bavli', 'mishnah'):
            self.assertIn(expected, identifiers)

    def test_manifest_excludes_translations_that_cannot_be_redistributed(self):
        document = lib.load_manifest(MANIFEST)
        listed = ' '.join(text['title'].lower() for text in document['texts'])
        for restricted in ('english standard version', 'new international',
                           'new american standard', 'new king james'):
            self.assertNotIn(restricted, listed)
        self.assertIn('cannot be redistributed', document['note'])

    def test_rejects_a_source_it_cannot_fetch(self):
        document = json.loads(MANIFEST.read_text())
        document['texts'][1]['source'] = 'carrier-pigeon'
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(document, handle)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        with self.assertRaises(ValueError):
            lib.load_manifest(handle.name)


class ReaderTests(unittest.TestCase):
    def test_bundled_text_resolves_without_an_install(self):
        self.assertEqual(scripture.Bible.resolve(ASSETS, 'kjv').name, 'kjv.tsv.gz')

    def test_an_unsafe_identifier_is_refused(self):
        with self.assertRaises(ValueError):
            scripture.Bible.resolve(ASSETS, '../../etc/passwd')

    def test_a_missing_translation_says_how_to_install_it(self):
        with self.assertRaisesRegex(ValueError, 'scripture-library install'):
            scripture.Bible.resolve(ASSETS, 'not-installed-here')

    def test_available_translations_always_offer_the_bundled_text(self):
        found = scripture.available_translations(ASSETS, root=Path('/nonexistent'))
        self.assertEqual([item['id'] for item in found], ['kjv'])


class WitnessTests(unittest.TestCase):
    def test_every_quote_is_complete_and_attributed(self):
        quotes = scripture.load_witnesses(ASSETS)
        self.assertGreaterEqual(len(quotes), 20)
        for entry in quotes:
            self.assertTrue(entry['source'].strip(), entry['id'])
            self.assertTrue(entry['author'].strip(), entry['id'])

    def test_a_disputed_attribution_says_so(self):
        quotes = {entry['id']: entry for entry in scripture.load_witnesses(ASSETS)}
        napoleon = quotes['napoleon']
        self.assertIn('disput', (napoleon['source'] + napoleon['note']).lower())

    def test_the_daily_quote_walks_the_whole_set(self):
        import datetime as dt
        quotes = scripture.load_witnesses(ASSETS)
        seen = {scripture.daily_witness(quotes, dt.date(2026, 1, 1) + dt.timedelta(days=day))['id']
                for day in range(len(quotes))}
        self.assertEqual(len(seen), len(quotes))

    def test_rejects_a_quote_missing_its_source(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        (Path(temp.name) / 'witnesses.json').write_text(json.dumps(
            {'quotes': [{'id': 'a', 'quote': 'q', 'author': 'x', 'note': 'n', 'stance': 's'}]}))
        with self.assertRaises(ValueError):
            scripture.load_witnesses(temp.name)


if __name__ == '__main__':
    unittest.main()
