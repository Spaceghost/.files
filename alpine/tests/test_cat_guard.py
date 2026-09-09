"""A cat parks the keyboard herself, and keeps it for the sitting."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
SERVICE = REPO / 'alpine/desktop/.local/bin/oldbook-cat'
sys.path.insert(0, str(LIBRARY))

FAKE_WATCH = '''\
import os, sys
with open(os.environ['GUARD_LOG'], 'a') as stream:
    stream.write(sys.argv[1] + '\\n')
sys.exit(int(os.environ.get('GUARD_' + sys.argv[1].upper() + '_STATUS', '0')))
'''

CAT = {'present': True, 'deciding': True, 'vetoed': False, 'confidence': 0.9,
       'keys_down': 6, 'patch': True, 'signals': [], 'corroboration': ['stillness']}
GONE = dict(CAT, present=False, deciding=False, confidence=0.0)
# The linger: she has shifted her weight, so presence holds without a fresh
# decision. The guard must not flap in that gap.
SETTLING = dict(CAT, deciding=False, confidence=0.0)


def load_service():
    loader = importlib.machinery.SourceFileLoader('oldbook_cat', str(SERVICE))
    specification = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(specification)
    loader.exec_module(module)
    return module


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'run').mkdir(mode=0o700)
        self.watch = self.root / 'fake-watch'
        self.watch.write_text(FAKE_WATCH)
        self.log = self.root / 'guard.log'
        for name, value in (('XDG_RUNTIME_DIR', str(self.root / 'run')),
                            ('OLDBOOK_LOCK_RECORD', str(self.root / 'absent.json')),
                            ('OLDBOOK_CAT_WATCH_COMMAND', str(self.watch)),
                            ('GUARD_LOG', str(self.log))):
            os.environ[name] = value
            self.addCleanup(os.environ.pop, name, None)
        self.config = self.root / 'cat.json'
        # An interaction with no implementation, so a whole tick can be taken
        # without ever making this laptop warm to prove a point about input.
        self.config.write_text(json.dumps(
            {'version': 1, 'enabled': True, 'selected': 'purr', 'work': [],
             'interactions': [{'id': 'purr', 'title': 'Purr', 'date': '2026-09-10',
                               'handler': 'purr', 'summary': 'x'}]}))
        self.module = load_service()
        self.module.hold_lid = self.fake_hold
        self.service = self.module.Service(config=self.config)
        self.addCleanup(lambda: self.service.lid(False))
        self.locked = False
        self.module.session_locked = lambda: self.locked

    def fake_hold(self):
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        return write_fd

    def calls(self):
        return self.log.read_text().split() if self.log.exists() else []

    def tick(self, judgement, when=1000.0):
        self.service.presence.judge = lambda now: dict(judgement)
        return self.service.tick(when)

    def test_a_decided_cat_on_an_unlocked_session_parks_the_keyboard(self):
        record = self.tick(CAT)

        self.assertEqual(self.calls(), ['start'])
        self.assertTrue(record['guard_engaged'])
        self.assertTrue(record['input_parked'])
        self.assertTrue(record['present'])
        self.assertFalse(record['locked'])

    def test_a_locked_session_already_parks_it_and_needs_no_guard(self):
        self.locked = True
        record = self.tick(CAT)

        self.assertEqual(self.calls(), [])
        self.assertFalse(record['guard_engaged'])
        self.assertTrue(record['input_parked'])
        self.assertTrue(record['present'])

    def test_the_keyboard_stays_parked_so_she_can_come_back(self):
        self.tick(CAT)
        record = self.tick(GONE, when=1002.0)

        # She is off the keys, so nothing is warmed; but the desktop is still
        # hers, because a cat that has got up has not necessarily left.
        self.assertEqual(self.calls(), ['start'])
        self.assertTrue(record['guard_engaged'])
        self.assertTrue(record['input_parked'])
        self.assertFalse(record['present'])

    def test_she_is_warmed_again_when_she_returns(self):
        self.tick(CAT)
        self.assertFalse(self.tick(GONE, when=1002.0)['present'])
        record = self.tick(CAT, when=1004.0)

        self.assertEqual(self.calls(), ['start'], 'the guard was never re-taken')
        self.assertTrue(record['present'])

    def test_shifting_her_weight_does_not_hand_the_keyboard_back(self):
        self.tick(CAT)
        record = self.tick(SETTLING, when=1002.0)

        self.assertEqual(self.calls(), ['start'])
        self.assertTrue(record['guard_engaged'])
        self.assertTrue(record['present'])

    def test_engaging_twice_is_one_guard(self):
        self.tick(CAT)
        self.tick(CAT, when=1002.0)

        self.assertEqual(self.calls(), ['start'])

    def test_a_guard_that_will_not_start_is_a_refusal_to_warm(self):
        os.environ['GUARD_START_STATUS'] = '1'
        self.addCleanup(os.environ.pop, 'GUARD_START_STATUS', None)
        record = self.tick(CAT)

        self.assertEqual(self.calls(), ['start'])
        self.assertFalse(record['guard_engaged'])
        self.assertFalse(record['input_parked'])
        self.assertFalse(record['present'], 'a machine that will not park input is not warmed')
        self.assertIn('would not start', record['guard_refusal'])

    def test_a_guard_this_daemon_did_not_engage_is_never_released(self):
        guard = self.module.InputGuard(self.watch)

        guard.release()

        self.assertEqual(self.calls(), [], 'the user parked their own inputs')

    def test_only_the_user_or_the_watcher_stopping_takes_the_guard_back(self):
        guard = self.module.InputGuard(self.watch)
        self.assertTrue(guard.engage())

        guard.release()

        self.assertFalse(guard.engaged)
        self.assertEqual(self.calls(), ['start', 'stop'])

    def test_a_guard_that_will_not_let_go_says_so(self):
        guard = self.module.InputGuard(self.watch)
        self.assertTrue(guard.engage())
        os.environ['GUARD_STOP_STATUS'] = '1'
        self.addCleanup(os.environ.pop, 'GUARD_STOP_STATUS', None)

        guard.release()

        self.assertFalse(guard.engaged)
        self.assertIn('would not stop', guard.refusal)

    def test_the_feature_being_off_never_takes_the_keyboard(self):
        document = json.loads(self.config.read_text())
        document['enabled'] = False
        self.config.write_text(json.dumps(document))
        record = self.tick(CAT)

        self.assertEqual(self.calls(), [])
        self.assertFalse(record['input_parked'])
        self.assertFalse(record['present'])

    def test_the_watcher_hands_the_keyboard_back_before_it_tidies_anything(self):
        # The one failure this feature must never have is dying while holding
        # the user's input, so the release sits in the shutdown path above the
        # lid, the devices and the parting record.
        source = SERVICE.read_text()
        shutdown = source.split("self.bed.stop('the watcher is stopping')", 1)[1]
        release = shutdown.index('self.guard.release(')
        self.assertLess(release, shutdown.index('self.lid(False)'))
        self.assertLess(release, shutdown.index('self.close_devices()'))


if __name__ == '__main__':
    unittest.main()
