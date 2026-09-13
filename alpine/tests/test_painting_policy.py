"""Nothing is painted unless a person asks for a painting by name.

Jack: "I want to freely generate themes even without the image gen. In fact,
if you can't switch the bg generator to use a different freeer api or set up my
alienware to generate images for you, then temporarily disable it for
theme-gen and elsewhere unless called specifically." The policy file is the
switch; the shipped default is off both ways; explicit requests are untouched.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_wallpapers import REPO, generator, load
import test_themed_artwork

painting_policy = load('painting_policy', REPO / 'alpine/wallpapers/painting_policy.py')


class PolicyFileTests(unittest.TestCase):
    def test_the_shipped_default_switches_both_kinds_off(self):
        shipped = REPO / 'alpine/desktop/.config/oldbook/painting.json'
        document = json.loads(shipped.read_text())
        self.assertEqual({key: document[key] for key in painting_policy.DEFAULTS},
                         {'scheduled': False, 'debut_painting': False})
        self.assertEqual(painting_policy.load(shipped), painting_policy.DEFAULTS)

    def test_a_missing_or_broken_file_is_the_default_not_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(painting_policy.load(root / 'absent.json'), painting_policy.DEFAULTS)
            (root / 'broken.json').write_text('{not json')
            self.assertEqual(painting_policy.load(root / 'broken.json'), painting_policy.DEFAULTS)
            (root / 'list.json').write_text('[true]')
            self.assertEqual(painting_policy.load(root / 'list.json'), painting_policy.DEFAULTS)
            (root / 'typed.json').write_text(json.dumps({'scheduled': 'yes', 'debut_painting': 1}))
            self.assertEqual(painting_policy.load(root / 'typed.json'), painting_policy.DEFAULTS)

    def test_each_switch_is_read_on_its_own(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'painting.json'
            source.write_text(json.dumps({'debut_painting': True, 'unknown': True}))
            self.assertTrue(painting_policy.allows('debut_painting', source))
            self.assertFalse(painting_policy.allows('scheduled', source))
            with self.assertRaises(ValueError):
                painting_policy.allows('manual', source)

    def test_the_users_copy_lives_under_the_oldbook_configuration(self):
        with mock.patch.dict(painting_policy.os.environ, {'XDG_CONFIG_HOME': '/tmp/probe-config'}):
            self.assertEqual(painting_policy.path(), Path('/tmp/probe-config/oldbook/painting.json'))

    def test_the_refusal_says_what_was_not_painted_and_where_to_change_it(self):
        text = painting_policy.refusal('scheduled', '/tmp/probe/painting.json')
        self.assertIn('"scheduled"', text)
        self.assertIn('/tmp/probe/painting.json', text)
        self.assertIn('explicit request still paints', text.casefold())


class GeneratorGateTests(unittest.TestCase):
    """The schedule obeys the switch; a manual request never consults it."""

    def setUp(self):
        self.fixture = test_themed_artwork.ThemedArtworkTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.stack.enter_context(mock.patch.object(generator, 'notify'))
        self.fixture.stack.enter_context(mock.patch.object(generator.time, 'sleep'))
        self.fixture.stack.enter_context(mock.patch.object(
            generator.subprocess, 'run',
            return_value=generator.subprocess.CompletedProcess([], 0, 'Logged in using ChatGPT', '')))

    def policy(self, **switches):
        return mock.patch.object(generator.painting_policy, 'load',
                                 return_value={**painting_policy.DEFAULTS, **switches})

    def test_a_scheduled_run_paints_nothing_and_reserves_nothing_while_off(self):
        with self.policy(scheduled=False), \
                mock.patch.object(generator, 'generate_native') as paint:
            self.assertEqual(generator.run_once(), 0)
        paint.assert_not_called()
        self.assertEqual([p.name for p in self.fixture.state.glob('????-??-??.json')], [])

    def test_switching_the_schedule_on_paints_the_same_day(self):
        with self.policy(scheduled=True), \
                mock.patch.object(generator, 'generate_native', return_value=str(self.fixture.native)) as paint, \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'):
            self.assertEqual(generator.run_once(), 0)
        paint.assert_called_once()

    def test_a_manual_request_paints_whatever_the_policy_says(self):
        with self.policy(scheduled=False, debut_painting=False), \
                mock.patch.object(generator, 'generate_native', return_value=str(self.fixture.native)) as paint, \
                mock.patch.object(generator, 'checkpoint_generated', return_value='abc123'):
            self.assertEqual(generator.run_once(manual=True), 0)
        paint.assert_called_once()

    def test_a_pending_checkpoint_is_still_repaired_while_off(self):
        pending = self.fixture.state / 'manual'
        pending.mkdir()
        record = pending / '1-1.json'
        record.write_text(json.dumps({'status': 'checkpoint-pending', 'file': 'x.png'}))
        with self.policy(scheduled=False), \
                mock.patch.object(generator, 'checkpoint_record', return_value=0) as repair, \
                mock.patch.object(generator, 'generate_native') as paint:
            self.assertEqual(generator.run_once(), 0)
        repair.assert_called_once()
        paint.assert_not_called()


if __name__ == '__main__':
    unittest.main()
