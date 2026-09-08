"""The persistent GPU keeper must be released when the carousel daemon stops."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
from carousel import Controller


class GraphicsLifecycle(unittest.TestCase):
    def test_stop_releases_warmed_graphics_after_dismissing_popup(self):
        events = []
        controller = Controller.__new__(Controller)
        controller.stopping = False
        controller.dismiss = lambda: events.append('popup dismissed')
        controller.graphics_primer = SimpleNamespace(close=lambda: events.append('graphics closed'))
        controller.loop = SimpleNamespace(quit=lambda: events.append('loop quit'))
        controller.stop()
        controller.stop()
        self.assertEqual(events, ['popup dismissed', 'graphics closed', 'loop quit'])
        self.assertIsNone(controller.graphics_primer)


if __name__ == '__main__':
    unittest.main()
