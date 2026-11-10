import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / '.bin/spaceghost-xiv-status'
loader = importlib.machinery.SourceFileLoader('xiv_status', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
status = importlib.util.module_from_spec(spec)
loader.exec_module(status)


class StatusTests(unittest.TestCase):
    def snapshot(self):
        return {'updated': 1000, 'source': 'fedora', 'online': True,
                'job': 'ACN', 'level': 18, 'hp': 100, 'state': 'READY',
                'zone': 'Western La Noscea', 'area': 'Skull Valley', 'coords': '27.7,25.5',
                'music': {'playing': True, 'title': 'A Song', 'artist': 'An Artist',
                          'positionSeconds': 60, 'lengthSeconds': 200, 'updated': 1000}}

    def test_live_includes_game_location_and_exact_song(self):
        line = status.render(self.snapshot(), 180, now=1005)
        for value in ['ACN18', 'READY', 'Western La Noscea', 'A Song', '1:00/3:20']:
            self.assertIn(value, line)

    def test_stale_does_not_claim_live_combat_or_playback(self):
        data = self.snapshot()
        data['state'] = 'COMBAT'
        line = status.render(data, 180, now=1100)
        self.assertIn('STALE', line)
        self.assertNotIn('COMBAT', line)
        self.assertNotIn('PLAY', line)

    def test_pause_and_independently_stale_music(self):
        data = self.snapshot()
        data['music']['playing'] = False
        self.assertIn('PAUSE', status.render(data, 180, now=1005))
        data['music']['updated'] = 900
        self.assertIn('PIANO unavailable', status.render(data, 180, now=1005))

    def test_untrusted_names_cannot_inject_tmux_or_terminal_sequences(self):
        text = status.clean('song #[fg=red] #{pane_id}\n\x1b[31m', 100)
        self.assertNotIn('#', text)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\n', text)

    def test_narrow_bar_keeps_location_and_track_within_width(self):
        import re
        line = status.render(self.snapshot(), 80, now=1005)
        plain = re.sub(r'#\[[^]]*\]', '', line)
        self.assertLessEqual(len(plain), 80)
        self.assertIn('A Song', plain)
        self.assertIn('Western', plain)

    def test_empty_is_honestly_offline(self):
        self.assertIn('unavailable', status.render({}, 80, now=1005))


if __name__ == '__main__':
    unittest.main()
