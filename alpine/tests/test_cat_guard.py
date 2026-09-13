"""Catbed mode is the user's: the watcher reads it and never touches it."""
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
import watch_mode  # noqa: E402

CAT = {'present': True, 'deciding': True, 'vetoed': False, 'confidence': 0.9,
       'keys_down': 6, 'patch': True, 'signals': [], 'corroboration': ['stillness']}
GONE = dict(CAT, present=False, deciding=False, confidence=0.0)
# The linger: she has shifted her weight, so presence holds without a fresh
# decision.
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
        self.runtime = self.root / 'run'
        self.runtime.mkdir(mode=0o700)
        for name, value in (('XDG_RUNTIME_DIR', str(self.runtime)),
                            ('OLDBOOK_LOCK_RECORD', str(self.root / 'absent.json'))):
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

    def park(self):
        """The user pressed Super+Shift+Escape: the guard's own live record."""
        watch_mode.publish({'process': watch_mode.process_identity(os.getpid()),
                            'engaged_at': 1.0, 'mode': watch_mode.SWAY_MODE}, str(self.runtime))

    def guard_record(self):
        return watch_mode.engaged(str(self.runtime))

    def tick(self, judgement, when=1000.0):
        self.service.presence.judge = lambda now: dict(judgement)
        return self.service.tick(when)

    def test_a_decided_cat_on_a_live_desktop_is_not_warmed_and_nothing_is_taken(self):
        record = self.tick(CAT)

        self.assertFalse(record['guard_engaged'])
        self.assertFalse(record['input_parked'])
        self.assertFalse(record['present'], 'a live desktop means a person, whatever the keys say')
        self.assertIsNone(self.guard_record(), 'the watcher must never engage the guard')

    def test_a_locked_session_parks_input(self):
        self.locked = True
        record = self.tick(CAT)

        self.assertTrue(record['locked'])
        self.assertTrue(record['input_parked'])
        self.assertFalse(record['guard_engaged'])
        self.assertTrue(record['present'])

    def test_catbed_mode_the_user_engaged_parks_input(self):
        self.park()
        record = self.tick(CAT)

        self.assertTrue(record['guard_engaged'])
        self.assertTrue(record['input_parked'])
        self.assertTrue(record['present'])
        self.assertFalse(record['locked'])

    def test_her_getting_up_releases_nothing(self):
        self.park()
        self.tick(CAT)
        record = self.tick(GONE, when=1002.0)

        self.assertFalse(record['present'], 'off the keys, so nothing is warmed')
        self.assertTrue(record['guard_engaged'], 'but catbed mode is still up')
        self.assertIsNotNone(self.guard_record())

    def test_shifting_her_weight_keeps_her_warm(self):
        self.park()
        self.tick(CAT)
        record = self.tick(SETTLING, when=1002.0)

        self.assertTrue(record['present'])
        self.assertTrue(record['guard_engaged'])

    def test_she_is_warmed_again_when_she_returns(self):
        self.park()
        self.tick(CAT)
        self.assertFalse(self.tick(GONE, when=1002.0)['present'])
        self.assertTrue(self.tick(CAT, when=1004.0)['present'])

    def test_a_stale_guard_record_is_not_catbed_mode(self):
        watch_mode.publish({'process': {'pid': 2 ** 22 - 1, 'start_time': '1', 'boot_id': 'x'},
                            'engaged_at': 1.0, 'mode': watch_mode.SWAY_MODE}, str(self.runtime))
        record = self.tick(CAT)

        self.assertFalse(record['guard_engaged'])
        self.assertFalse(record['present'])

    def test_the_feature_being_off_never_counts_her(self):
        document = json.loads(self.config.read_text())
        document['enabled'] = False
        self.config.write_text(json.dumps(document))
        self.park()
        record = self.tick(CAT)

        self.assertFalse(record['present'])
        self.assertIsNotNone(self.guard_record(), 'and the feature being off touches nothing')

    def test_the_watcher_never_starts_or_stops_the_guard(self):
        source = SERVICE.read_text()
        for forbidden in ('InputGuard', 'guard.engage', 'guard.release', "'oldbook-watch'",
                          'OLDBOOK_CAT_WATCH_COMMAND'):
            self.assertNotIn(forbidden, source)
        self.assertIn('watch_mode.engaged()', source, 'the guard is read from its own record')


if __name__ == '__main__':
    unittest.main()
