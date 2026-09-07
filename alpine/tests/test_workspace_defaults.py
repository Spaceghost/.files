import runpy
from pathlib import Path
import unittest

MODEL = Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook/workspace_defaults.py'


class WorkspaceDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODEL.exists(), 'workspace defaults model is missing')
        self.model = runpy.run_path(str(MODEL))

    def test_first_instance_moves_once_and_extras_stay_put(self):
        placement = self.model['Placement']()
        self.assertEqual(placement.plan([(10, 'Firefox')]), [(10, 5)])
        self.assertEqual(placement.plan([(10, 'Firefox'), (11, 'Firefox')]), [])
        # Closing the designated window does not adopt an existing extra window.
        self.assertEqual(placement.plan([(11, 'Firefox')]), [])
        self.assertEqual(placement.plan([(11, 'Firefox'), (12, 'Firefox')]), [(12, 5)])

    def test_restart_keeps_manual_moves_and_pending_terminal_identity(self):
        placement = self.model['Placement']()
        placement.plan([(10, 'Codex')])
        restored = self.model['Placement'](placement.state())
        self.assertEqual(restored.plan([(10, 'Codex'), (11, 'Terminal')]), [])
        self.assertEqual(restored.plan([(10, 'Codex'), (11, 'claude')]), [(11, 3)])

    def test_initial_existing_windows_are_adopted_without_moving(self):
        placement = self.model['Placement']()
        self.assertEqual(placement.plan([(1, 'Pithos'), (2, 'Pithos')], adopt=True), [])
        self.assertEqual(placement.plan([(1, 'Pithos'), (2, 'Pithos'), (3, 'Pithos')]), [])

    def test_rotations_avoid_other_workspace_choices_and_wrap(self):
        choose = self.model['choose_artwork']
        self.assertEqual(choose(['a', 'b', 'c', 'd'], 'a', 1, {'b', 'c'}), 'd')
        self.assertEqual(choose(['a', 'b', 'c', 'd'], 'a', -1, {'d'}), 'c')
        self.assertEqual(choose(['a', 'b'], 'a', 1, {'b'}), 'a')


if __name__ == '__main__':
    unittest.main()
