"""The caption's agent-state glyph: two honest signals, no invented motion."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop/.local/lib/oldbook'))
import agent_status
import loading


def record(event='attention', valid_until=1_000, **extra):
    return {'event': event, 'valid_until': valid_until, **extra}


class Matching(unittest.TestCase):
    def test_matches_by_tty_first(self):
        identity = {'tty': '/dev/pts/3', 'tmux_pane': '%9'}
        self.assertTrue(agent_status.matches(identity, record(tty='/dev/pts/3', tmux_pane='%2')))
        self.assertFalse(agent_status.matches(identity, record(tty='/dev/pts/4', tmux_pane='%9')))

    def test_falls_back_to_pane_when_no_tty(self):
        identity = {'tmux_pane': '%9'}
        self.assertTrue(agent_status.matches(identity, record(tmux_pane='%9')))
        self.assertFalse(agent_status.matches(identity, record(tmux_pane='%2')))

    def test_neither_tty_nor_pane_never_matches(self):
        self.assertFalse(agent_status.matches({}, record(tty='/dev/pts/3')))


class Waiting(unittest.TestCase):
    def test_true_only_for_a_waiting_event_on_a_matching_record(self):
        identity = {'tty': '/dev/pts/3'}
        self.assertTrue(agent_status.waiting(identity, [record(event='attention', tty='/dev/pts/3')]))
        self.assertTrue(agent_status.waiting(
            identity, [record(event='permission-requested', tty='/dev/pts/3')]))

    def test_false_for_a_non_waiting_event(self):
        identity = {'tty': '/dev/pts/3'}
        self.assertFalse(agent_status.waiting(identity, [record(event='idle', tty='/dev/pts/3')]))

    def test_false_when_no_record_matches_this_window(self):
        identity = {'tty': '/dev/pts/3'}
        self.assertFalse(agent_status.waiting(identity, [record(tty='/dev/pts/9')]))


class Glyph(unittest.TestCase):
    def test_none_for_a_window_that_is_not_an_agent(self):
        self.assertIsNone(agent_status.glyph({'kind': 'app'}, []))
        self.assertIsNone(agent_status.glyph({'kind': None}, []))

    def test_waiting_wins_over_a_reported_state(self):
        identity = {'kind': 'codex', 'tty': '/dev/pts/3', 'state': 'Thinking'}
        glyph = agent_status.glyph(identity, [record(tty='/dev/pts/3')])
        self.assertEqual(glyph, agent_status.WAITING)
        self.assertEqual(glyph, loading.MARKS['blocked'])

    def test_codex_with_a_state_and_nothing_waiting_reads_as_working(self):
        identity = {'kind': 'codex', 'tty': '/dev/pts/3', 'state': 'Thinking'}
        self.assertEqual(agent_status.glyph(identity, []), agent_status.WORKING)

    def test_codex_with_no_state_and_nothing_waiting_shows_nothing(self):
        identity = {'kind': 'codex', 'tty': '/dev/pts/3', 'state': None}
        self.assertIsNone(agent_status.glyph(identity, []))

    def test_claude_never_reports_working_only_waiting_or_nothing(self):
        # Claude embeds no run-state string, so this desktop shows a guess
        # dressed as a fact for no kind rather than making one up for Claude.
        waiting_identity = {'kind': 'claude', 'tty': '/dev/pts/3'}
        self.assertEqual(agent_status.glyph(waiting_identity, [record(tty='/dev/pts/3')]),
                         agent_status.WAITING)
        idle_identity = {'kind': 'claude', 'tty': '/dev/pts/3', 'state': 'anything'}
        self.assertIsNone(agent_status.glyph(idle_identity, []))

    def test_the_working_glyph_is_a_single_still_frame_not_an_animation(self):
        """agent_status never advances SPINNER on its own -- there is no clock
        here to advance it with, only ever loading.SPINNER[0]."""
        identity = {'kind': 'codex', 'tty': '/dev/pts/3', 'state': 'Thinking'}
        self.assertEqual(agent_status.glyph(identity, []), loading.SPINNER[0])


class LoadRecords(unittest.TestCase):
    def test_reads_every_unexpired_record_in_the_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.json').write_text('{"event": "attention", "valid_until": 500, "tty": "x"}')
            (root / 'b.json').write_text('{"event": "attention", "valid_until": 5, "tty": "y"}')
            records = agent_status.load_records(root, now=100)
            self.assertEqual([r['tty'] for r in records], ['x'])

    def test_a_corrupt_file_is_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bad.json').write_text('not json at all')
            (root / 'not-a-dict.json').write_text('[1, 2, 3]')
            self.assertEqual(agent_status.load_records(root, now=0), [])

    def test_a_missing_directory_reads_as_empty_not_an_error(self):
        self.assertEqual(agent_status.load_records('/no/such/directory', now=0), [])


if __name__ == '__main__':
    unittest.main()
