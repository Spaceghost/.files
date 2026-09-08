"""Graphics warmup belongs to the daemon lifetime, never a gesture callback."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/mbp_intel'))
import showdesktop


class ShowdesktopStartupTests(unittest.TestCase):
    def test_keeper_survives_the_event_loop_and_closes_on_failure(self):
        events = []
        keeper = Mock()
        keeper.close.side_effect = lambda: events.append('closed')
        graphics = types.SimpleNamespace(warm_graphics=lambda: (events.append('warm'), keeper)[1])
        priority = types.SimpleNamespace(request_priority=lambda: events.append('priority'))

        def run_loop(*_args):
            self.assertEqual(events, ['priority', 'warm', 'priority'])
            keeper.close.assert_not_called()
            raise RuntimeError('private loop failure')

        with patch.dict(sys.modules, graphics_warmup=graphics, ui_priority=priority), \
                patch.object(showdesktop, 'recover_state'), patch.object(showdesktop, 'warm_up'), \
                patch.object(showdesktop, 'serve_session', side_effect=run_loop, create=True):
            with self.assertRaisesRegex(RuntimeError, 'private loop failure'):
                showdesktop.serve(None, None, None, None)
        keeper.close.assert_called_once_with()
        self.assertEqual(events[-1], 'closed')

    def test_optional_warmup_failure_still_serves_gestures(self):
        graphics = types.SimpleNamespace(warm_graphics=Mock(side_effect=RuntimeError('no renderer')))
        priority = types.SimpleNamespace(request_priority=Mock())
        with patch.dict(sys.modules, graphics_warmup=graphics, ui_priority=priority), \
                patch.object(showdesktop, 'recover_state'), patch.object(showdesktop, 'warm_up'), \
                patch.object(showdesktop, 'serve_session', create=True) as loop, \
                patch('builtins.print'):
            showdesktop.serve(None, None, None, None)
        loop.assert_called_once_with(None, None, None, None)


if __name__ == '__main__':
    unittest.main()
