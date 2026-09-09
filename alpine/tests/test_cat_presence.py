"""Telling a cat on the keyboard from a person at it, and the record it leaves."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
sys.path.insert(0, str(LIBRARY))
import cat_presence as cp  # noqa: E402


def load_service():
    loader = importlib.machinery.SourceFileLoader(
        'oldbook_cat', str(REPO / 'alpine/desktop/.local/bin/oldbook-cat'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def code(name):
    return cp.KEY_CODES[name]


class Keyboard:
    """A tiny driver so a test can say 'a paw lands' instead of packing structs."""

    def __init__(self, contact_maximum=1000):
        self.presence = cp.Presence(contact_maximum=contact_maximum)
        self.now = 100.0

    def wait(self, seconds):
        self.now += seconds
        return self

    def press(self, *names):
        for name in names:
            self.presence.event(self.now, cp.EV_KEY, code(name), cp.KEY_DOWN)
        return self

    def release(self, *names):
        for name in names:
            self.presence.event(self.now, cp.EV_KEY, code(name), cp.KEY_UP)
        return self

    def repeat(self, *names):
        for name in names:
            self.presence.event(self.now, cp.EV_KEY, code(name), cp.KEY_REPEAT)
        return self

    def touch(self, value):
        self.presence.event(self.now, cp.EV_ABS, cp.ABS_MT_TOUCH_MAJOR, value)
        return self

    def type_words(self, keys, hold=0.08, gap=0.12):
        for name in keys:
            self.press(name).wait(hold).release(name).wait(gap)
        return self

    def judge(self):
        return self.presence.judge(self.now)


class PersonTests(unittest.TestCase):
    """The false positive is the expensive one; these are the ways to make it."""

    def test_ordinary_typing_is_never_a_cat(self):
        board = Keyboard().type_words(['H', 'E', 'L', 'L', 'O', 'SPACE', 'T', 'H', 'E', 'R', 'E'])
        self.assertFalse(board.judge()['present'])

    def test_a_four_key_chord_is_a_person_however_long_it_is_held(self):
        board = Keyboard().press('LEFTCTRL', 'LEFTSHIFT', 'LEFTALT', 'K').wait(30)
        judgement = board.judge()
        self.assertFalse(judgement['present'])
        self.assertFalse(judgement['signals'] and 'simultaneity' in judgement['signals'])

    def test_a_forearm_across_the_keys_still_loses_to_recent_typing(self):
        """The veto outranks everything: someone typing a moment ago is present."""
        board = Keyboard().type_words(['P', 'A', 'S', 'S'])
        board.press('A', 'S', 'D', 'F', 'G', 'H').wait(5)
        judgement = board.judge()
        self.assertTrue(judgement['vetoed'])
        self.assertFalse(judgement['present'])

    def test_the_veto_lapses_once_the_typing_is_genuinely_old(self):
        board = Keyboard().type_words(['P', 'A', 'S', 'S'])
        board.wait(cp.VETO_WINDOW + 1).press('A', 'S', 'D', 'F', 'G', 'H')
        board.wait(cp.PERSISTENCE + 0.5)
        self.assertTrue(board.judge()['present'])

    def test_a_held_crowd_is_not_enough_before_it_has_persisted(self):
        board = Keyboard().press('A', 'S', 'D', 'F', 'G').wait(cp.PERSISTENCE - 0.5)
        self.assertFalse(board.judge()['present'])

    def test_a_crowd_that_breaks_up_restarts_the_clock(self):
        board = Keyboard().press('A', 'S', 'D', 'F', 'G').wait(1.5).release('G')
        board.wait(1.5).press('G').wait(1.0)
        self.assertFalse(board.judge()['present'])


class CatTests(unittest.TestCase):
    def test_a_paw_on_six_contiguous_keys_is_a_cat(self):
        board = Keyboard().press('S', 'D', 'F', 'X', 'C', 'V').wait(cp.PERSISTENCE + 1)
        judgement = board.judge()
        self.assertTrue(judgement['present'])
        self.assertIn('contiguity', judgement['corroboration'])
        self.assertGreaterEqual(judgement['confidence'], 0.6)

    def test_scattered_keys_still_count_when_nothing_is_being_typed(self):
        """Five keys held for two seconds with no typing anywhere near is not a person."""
        board = Keyboard().press('Q', 'P', 'B', 'F12', 'RIGHT').wait(cp.PERSISTENCE + 1)
        judgement = board.judge()
        self.assertTrue(judgement['present'])
        self.assertEqual(judgement['corroboration'], ['stillness'])

    def test_the_autorepeat_storm_corroborates(self):
        board = Keyboard().press('A', 'S', 'D', 'F', 'G').wait(cp.PERSISTENCE + 1)
        board.repeat('A', 'S', 'D')
        self.assertIn('drumming', board.judge()['corroboration'])

    def test_a_contact_far_too_large_for_a_finger_corroborates(self):
        board = Keyboard(contact_maximum=1000).press('Q', 'P', 'B', 'F12', 'RIGHT')
        board.touch(800).wait(cp.PERSISTENCE + 0.5)
        self.assertIn('contact', board.judge()['corroboration'])

    def test_a_fingertip_sized_contact_does_not(self):
        board = Keyboard(contact_maximum=1000).press('Q', 'P', 'B', 'F12', 'RIGHT')
        board.touch(90).wait(cp.PERSISTENCE + 0.5)
        self.assertNotIn('contact', board.judge()['corroboration'])

    def test_a_device_with_no_scale_contributes_no_contact_evidence(self):
        board = Keyboard(contact_maximum=None).press('Q', 'P', 'B', 'F12', 'RIGHT')
        board.touch(100000).wait(cp.PERSISTENCE + 0.5)
        self.assertNotIn('contact', board.judge()['corroboration'])

    def test_she_shifts_her_weight_without_leaving(self):
        """The linger is what stops the thirty-second question flapping."""
        board = Keyboard().press('S', 'D', 'F', 'X', 'C', 'V').wait(cp.PERSISTENCE + 1)
        self.assertTrue(board.judge()['present'])
        board.release('S', 'D', 'F', 'X', 'C', 'V').wait(cp.LINGER - 1)
        self.assertTrue(board.judge()['present'])
        board.wait(2)
        self.assertFalse(board.judge()['present'])

    def test_confidence_rises_with_agreement_and_is_zero_when_absent(self):
        one = Keyboard().press('Q', 'P', 'B', 'F12', 'RIGHT').wait(cp.PERSISTENCE + 1).judge()
        many = Keyboard().press('S', 'D', 'F', 'X', 'C', 'V').wait(cp.PERSISTENCE + 1)
        many.repeat('S', 'D', 'F')
        self.assertGreater(many.judge()['confidence'], one['confidence'])
        self.assertEqual(Keyboard().judge()['confidence'], 0.0)


class BoardTests(unittest.TestCase):
    def test_neighbours_touch_along_a_row_and_across_rows(self):
        self.assertTrue(cp.adjacent(code('S'), code('D')))
        self.assertTrue(cp.adjacent(code('D'), code('E')))
        self.assertFalse(cp.adjacent(code('A'), code('L')))
        self.assertFalse(cp.adjacent(code('ESC'), code('SPACE')))

    def test_a_patch_is_measured_not_merely_counted(self):
        paw = {code(name) for name in ('S', 'D', 'F', 'X', 'C', 'V')}
        self.assertEqual(cp.largest_patch(paw), 6)
        scattered = {code(name) for name in ('Q', 'P', 'B', 'F12', 'RIGHT')}
        self.assertLess(cp.largest_patch(scattered), cp.CONTIGUOUS)

    def test_unknown_codes_are_ignored_rather_than_guessed_at(self):
        self.assertEqual(cp.largest_patch({60000, 60001}), 0)
        self.assertFalse(cp.adjacent(60000, code('A')))


class WireTests(unittest.TestCase):
    def packed(self, *events):
        return b''.join(cp.EVENT.pack(0, 0, kind, key, value) for kind, key, value in events)

    def test_a_read_is_decoded_into_the_judgement(self):
        presence = cp.Presence()
        presence.feed(1.0, self.packed(*[(cp.EV_KEY, code(name), cp.KEY_DOWN)
                                         for name in ('S', 'D', 'F', 'X', 'C', 'V')]))
        self.assertTrue(presence.judge(1.0 + cp.PERSISTENCE + 1)['present'])

    def test_a_torn_read_drops_the_partial_event_rather_than_misreading_it(self):
        presence = cp.Presence()
        data = self.packed(*[(cp.EV_KEY, code(name), cp.KEY_DOWN)
                             for name in ('S', 'D', 'F', 'X', 'C', 'V')])
        presence.feed(1.0, data[:-3])
        self.assertEqual(presence.judge(1.0)['keys_down'], 5)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)

    def test_the_record_round_trips_through_the_runtime_directory(self):
        cp.publish({'present': True, 'last_seen': 1000.0}, runtime=self.runtime)
        written = json.loads((self.runtime / 'oldbook/cat.json').read_text())
        self.assertTrue(written['present'])

    def test_the_thirty_second_question_is_answered_from_the_record_alone(self):
        record = {'last_seen': 1000.0}
        self.assertTrue(cp.seen_within(30, record=record, now=1029.0))
        self.assertFalse(cp.seen_within(30, record=record, now=1031.0))

    def test_a_stamp_from_the_future_or_from_nothing_is_not_a_cat(self):
        self.assertFalse(cp.seen_within(30, record={'last_seen': 2000.0}, now=1000.0))
        self.assertFalse(cp.seen_within(30, record={'last_seen': None}, now=1000.0))
        self.assertFalse(cp.seen_within(30, record={}, now=1000.0))
        self.assertFalse(cp.seen_within(30, record={'last_seen': 'soon'}, now=1000.0))

    def test_a_missing_record_reads_as_no_cat_rather_than_an_error(self):
        record = cp.published(runtime=self.runtime / 'never')
        self.assertFalse(record['present'])
        self.assertFalse(record['running'])


class DeviceTests(unittest.TestCase):
    """Picking the internal keyboard and trackpad out of /proc/bus/input/devices."""

    PROC = '''I: Bus=0003 Vendor=05ac Product=8290 Version=0111
N: Name="Broadcom Corp. Bluetooth USB Host Controller"
H: Handlers=sysrq kbd leds event0

I: Bus=0003 Vendor=05ac Product=0274 Version=0110
N: Name="Apple Inc. Apple Internal Keyboard / Trackpad"
H: Handlers=sysrq kbd leds event2

I: Bus=0019 Vendor=0000 Product=0005 Version=0000
N: Name="Lid Switch"
H: Handlers=event3

I: Bus=0003 Vendor=05ac Product=0274 Version=0001
N: Name="bcm5974"
H: Handlers=mouse1 event7
'''

    def setUp(self):
        self.service = load_service()

    def test_the_internal_keyboard_and_the_trackpad_are_both_found(self):
        keyboard = self.service.event_nodes(self.service.KEYBOARD_HINTS, self.PROC, want_keys=True)
        trackpad = self.service.event_nodes(self.service.TRACKPAD_HINTS, self.PROC)
        self.assertEqual(keyboard, ['/dev/input/event2'])
        self.assertEqual(trackpad, ['/dev/input/event2', '/dev/input/event7'])

    def test_the_lid_switch_and_the_bluetooth_dongle_are_not_watched(self):
        chosen = set(self.service.event_nodes(self.service.KEYBOARD_HINTS, self.PROC,
                                              want_keys=True)
                     + self.service.event_nodes(self.service.TRACKPAD_HINTS, self.PROC))
        self.assertNotIn('/dev/input/event3', chosen)
        self.assertNotIn('/dev/input/event0', chosen)

    def test_a_machine_with_no_matching_device_yields_nothing_rather_than_guessing(self):
        self.assertEqual(self.service.event_nodes(self.service.KEYBOARD_HINTS, 'nonsense'), [])


if __name__ == '__main__':
    unittest.main()
