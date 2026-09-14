from pathlib import Path
import runpy
import unittest

REPO = Path(__file__).resolve().parents[2]


class BootGuardTests(unittest.TestCase):
    def setUp(self):
        self.api = runpy.run_path(str(REPO / 'alpine/security/catmode/oldbook-catmode'))

    def test_only_internal_devices_and_power_buttons_are_selected(self):
        matches = self.api['protected_name']
        self.assertTrue(matches('Apple Inc. Apple Internal Keyboard / Trackpad'))
        self.assertTrue(matches('bcm5974'))
        self.assertTrue(matches('Power Button'))
        self.assertFalse(matches('External USB Keyboard'))
        self.assertFalse(matches('Lid Switch'))

    def test_release_requires_exact_chord_then_all_keys_up(self):
        chord = self.api['ReleaseChord']()
        self.assertFalse(chord.update({125, 42, 1}, 0))
        self.assertFalse(chord.update({125, 42, 1, 30}, 2))
        self.assertFalse(chord.update({125, 42, 1}, 3))
        self.assertFalse(chord.update({125, 42, 1}, 4.1))
        self.assertFalse(chord.update({125, 42}, 4.15))
        self.assertFalse(chord.update({125}, 4.18))
        self.assertTrue(chord.update(set(), 4.2))

    def test_a_short_chord_does_not_release(self):
        chord = self.api['ReleaseChord']()
        self.assertFalse(chord.update({125, 42, 1}, 0))
        self.assertFalse(chord.update(set(), .5))

    def test_an_extra_key_cancels_an_already_held_chord(self):
        chord = self.api['ReleaseChord']()
        chord.update({125, 42, 1}, 0)
        chord.update({125, 42, 1}, 2)
        self.assertFalse(chord.update({125, 42, 1, 30}, 2.1))
        self.assertFalse(chord.update(set(), 2.2))

    def test_shutdown_inhibition_survives_process_exit_and_can_be_recovered(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            device = Path(root) / 'input2'
            device.mkdir()
            (device / 'name').write_text('Apple Internal Keyboard / Trackpad')
            (device / 'inhibited').write_text('0')
            self.api['inhibit'](True, Path(root))
            self.assertEqual((device / 'inhibited').read_text(), '1')
            self.api['inhibit'](False, Path(root))
            self.assertEqual((device / 'inhibited').read_text(), '0')


if __name__ == '__main__':
    unittest.main()
