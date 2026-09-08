"""The desktop is a slow information display; telemetry belongs in Waybar."""
import json
import importlib.machinery
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'alpine/desktop/.local/lib/oldbook'))
import conky_layout


class QuietPanelTests(unittest.TestCase):
    def load(self, panels, interval=2):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'panels.json'
            path.write_text(json.dumps({'panels': panels, 'update_interval': interval}))
            return conky_layout.load_panels(path)

    def panel(self, text, identifier='card'):
        return {'id': identifier, 'text': text, 'width': 200, 'height': 100}

    def test_restored_telemetry_is_filtered_even_under_an_unfamiliar_name(self):
        for variable in ('${cpu cpu1}', '$mem', '${top cpu 1}', '${diskio}',
                         '${downspeed wlan0}', '${hwmon 0 temp 1}', '${uptime}',
                         '${fs_used /}', '${wireless_essid wlan0}'):
            with self.subTest(variable=variable):
                document = self.load([self.panel('Date ${time %A}', 'date'),
                                      self.panel(variable)])
                self.assertEqual([p['id'] for p in document['panels']], ['date'])

    def test_useful_cards_and_mail_survive_with_slow_refresh(self):
        text = ('${battery_percent BAT0} ${time %A} '
                '${execpi 30 {{scripture}} panel --width 52} '
                '${execi 20 {{bin}} gallery-text} ${new_mails ~/Maildir}')
        document = self.load([self.panel(text)])
        self.assertEqual(document['update_interval'], 60)
        body = document['panels'][0]['text']
        self.assertIn('${execpi 60 ', body)
        self.assertIn('${execi 60 ', body)
        self.assertIn('${new_mails ~/Maildir}', body)

    def test_shipped_source_cannot_restore_stats_or_subminute_refresh(self):
        source = json.loads((REPO / 'alpine/desktop/.config/conky/panels.json').read_text())
        result = self.load(source['panels'], source['update_interval'])
        self.assertEqual(result['panels'], source['panels'])
        self.assertGreaterEqual(source['update_interval'], 60)
        self.assertFalse({'reactor','memory','storage','transmission'} &
                         {p['id'] for p in source['panels']})
        self.assertTrue({'power','gallery','ghost','masthead'} <=
                        {p['id'] for p in result['panels']})

    def test_missing_invalid_and_excessive_intervals_are_safe(self):
        for value in (None, 'invalid', -2, float('nan'), float('inf'), 1, 999):
            with self.subTest(value=value):
                interval = self.load([self.panel('Notes')], value)['update_interval']
                self.assertTrue(60 <= interval <= 300)

    def test_scripture_alone_keeps_the_explicit_hourly_interval(self):
        document = self.load([self.panel('${execpi 60 scripture panel}', 'scripture'),
                              self.panel('${execpi 3600 scripture witness}', 'witness'),
                              self.panel('${execpi 3600 journal panel}', 'ghost')])
        texts = {panel['id']: panel['text'] for panel in document['panels']}
        self.assertIn('${execpi 3600 ', texts['scripture'])
        self.assertIn('${execpi 300 ', texts['witness'])
        self.assertIn('${execpi 300 ', texts['ghost'])
        self.assertEqual(document['update_interval'], 60)

    def test_wallpaper_rebuild_and_cached_layout_cannot_restore_telemetry(self):
        helper = importlib.machinery.SourceFileLoader(
            'quiet_conky_helper', str(REPO / 'alpine/desktop/.local/bin/oldbook-conky')).load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'panels.json'
            image = root / 'wallpaper.png'
            image.write_bytes(b'wallpaper identity')
            safe = self.panel('${battery_percent BAT0}', 'power')
            source.write_text(json.dumps({'panels': [safe], 'update_interval': 60}))
            placement = {'id': 'power', 'x': 40, 'y': 80, 'width': 200,
                         'height': 100, 'background': [20, 20, 20]}
            with patch.object(helper, 'PANELS', source), \
                 patch.object(helper, 'hardware', return_value={}), \
                 patch.object(helper, 'wallpaper_path', return_value=image), \
                 patch.object(helper, 'screen_rectangle', return_value={
                     'width': 1440, 'height': 900, 'name': 'test', 'origin_y': 42}), \
                 patch.object(helper, 'load_theme', return_value={'id': 'test'}), \
                 patch.object(conky_layout, 'analyze_image', return_value={}) as analyze, \
                 patch.object(conky_layout, 'place_panels', return_value=[placement]):
                self.assertEqual(helper.build(root), ['power'])
                source.write_text(json.dumps({'panels': [safe, self.panel('${cpu}', 'reactor')],
                                              'update_interval': 2}))
                (root / 'reactor.conf').write_text('stale CPU config')
                self.assertEqual(helper.build(root), ['power'])
                expected_reads = 1 if hasattr(helper, 'pairing_key') else 2
                self.assertEqual(analyze.call_count, expected_reads)
                self.assertFalse((root / 'reactor.conf').exists())
                self.assertIn('update_interval = 60', (root / 'power.conf').read_text())


if __name__ == '__main__':
    unittest.main()
