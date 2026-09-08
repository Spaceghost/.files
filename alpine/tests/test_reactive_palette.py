"""The desktop accent follows the painting, inside the theme's own colours."""
import json
import math
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-palette'
THEME = json.loads((REPO / 'alpine/themes/gruvbox-dark.json').read_text())

sys.path.insert(0, str(LIBRARY))
import painting_palette


def write_png(path, pixels, width, height):
    """Save an RGB pixel list as a PNG through GdkPixbuf, which is always here."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf, GLib
    data = bytearray()
    for row in pixels:
        for red, green, blue in row:
            data += bytes((red, green, blue))
    pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(data)), GdkPixbuf.Colorspace.RGB, False, 8,
        width, height, width * 3)
    pixbuf.savev(str(path), 'png', [], [])
    return path


def painting(path, kind, edge=64):
    """A crude but honest stand-in for one of the gallery's moods."""
    rows = []
    for y in range(edge):
        row = []
        for x in range(edge):
            lift = y / edge
            if kind == 'sunset':
                # Amber sky burning down into a warm dark foreground.
                row.append((int(40 + 200 * lift), int(30 + 150 * lift), int(20 + 30 * lift)))
            elif kind == 'nocturne':
                # Deep blue night with a colder horizon; no warm light at all.
                row.append((int(15 + 25 * lift), int(30 + 60 * lift), int(60 + 130 * lift)))
            else:
                # Charcoal with a faint neutral gradient and no hue to speak of.
                value = int(40 + 60 * lift)
                row.append((value, value, value))
        rows.append(row)
    return write_png(path, rows, edge, edge)


class PaintingAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def analyse(self, kind):
        return painting_palette.analyse(painting(self.directory / (kind + '.png'), kind), THEME)

    def test_a_warm_painting_elects_a_warm_accent(self):
        record = self.analyse('sunset')
        self.assertIn(record['accent_name'], ('yellow', 'orange'))
        self.assertIn(record['accent'], THEME['palette'].values())

    def test_a_cool_painting_elects_a_cool_accent(self):
        record = self.analyse('nocturne')
        self.assertIn(record['accent_name'], ('blue', 'aqua', 'purple'))

    def test_a_neutral_painting_keeps_the_declared_accent(self):
        record = self.analyse('grey')
        self.assertEqual(record['accent'], THEME['palette']['yellow'])
        self.assertNotIn('accent_name', record)

    def test_the_accent_is_always_one_the_theme_declares(self):
        for kind in ('sunset', 'nocturne', 'grey'):
            record = self.analyse(kind)
            for key in ('accent', 'accent_secondary'):
                self.assertIn(record[key], THEME['palette'].values(),
                              kind + ' invented a colour for ' + key)

    def test_shares_partition_the_whole_histogram(self):
        hues = {'a': 0.0, 'b': math.pi}
        histogram = [0.0] * painting_palette.BINS
        histogram[0] = 0.25
        histogram[painting_palette.BINS // 2] = 0.75
        shares = painting_palette.shares(histogram, hues)
        self.assertAlmostEqual(shares['a'], 0.25)
        self.assertAlmostEqual(shares['b'], 0.75)

    def test_a_theme_without_candidates_keeps_its_accent(self):
        theme = {'palette': {'accent': '#abcdef'}}
        record = painting_palette.choose({'histogram': [0.0] * painting_palette.BINS,
                                          'mean_chroma': 0.3}, theme)
        self.assertEqual(record['accent'], '#abcdef')


class OverrideReaderTests(unittest.TestCase):
    """`read_palette` honours the record only when it is safe to."""

    def setUp(self):
        self.api = runpy.run_path(str(LIBRARY / 'overlay_theme.py'))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.themes = base / 'themes'
        self.themes.mkdir()
        self.state = base / 'state'
        (self.state / 'oldbook').mkdir(parents=True)
        previous = os.environ.get('XDG_STATE_HOME')
        os.environ['XDG_STATE_HOME'] = str(self.state)
        self.addCleanup(lambda: os.environ.__setitem__('XDG_STATE_HOME', previous)
                        if previous is not None else os.environ.pop('XDG_STATE_HOME', None))
        (self.themes / 'current').write_text('warm')
        self.descriptor = {'id': 'warm', 'palette': {
            'background': '#282828', 'foreground': '#ebdbb2',
            'yellow': '#fabd2f', 'blue': '#83a598', 'orange': '#fe8019'}}
        self.write_theme()
        self.record = self.state / 'oldbook/palette-override.json'

    def write_theme(self):
        (self.themes / 'warm.json').write_text(json.dumps(self.descriptor))

    def write_override(self, **fields):
        payload = {'theme': 'warm', 'accent': '#83a598', 'accent_secondary': '#fe8019'}
        payload.update(fields)
        self.record.write_text(json.dumps(payload))

    def accent(self):
        return self.api['read_palette'](self.themes)

    def test_without_a_record_the_declared_accent_stands(self):
        palette = self.accent()
        self.assertEqual(palette['accent'], '#fabd2f')
        self.assertEqual(palette['accent_secondary'], '#fabd2f')

    def test_a_record_moves_the_accent_and_its_companion(self):
        self.write_override()
        palette = self.accent()
        self.assertEqual(palette['accent'], '#83a598')
        self.assertEqual(palette['accent_secondary'], '#fe8019')

    def test_a_record_from_another_theme_is_ignored(self):
        self.write_override(theme='cool')
        self.assertEqual(self.accent()['accent'], '#fabd2f')

    def test_a_colour_the_theme_does_not_own_is_ignored(self):
        self.write_override(accent='#ff00ff')
        self.assertEqual(self.accent()['accent'], '#fabd2f')

    def test_a_broken_record_never_blanks_the_palette(self):
        self.record.write_text('{ not json at all')
        palette = self.accent()
        self.assertEqual(palette['accent'], '#fabd2f')
        self.assertEqual(palette['background'], '#282828')

    def test_the_descriptor_can_opt_out(self):
        self.write_override()
        self.descriptor['reactive_accent'] = False
        self.write_theme()
        self.assertEqual(self.accent()['accent'], '#fabd2f')

    def test_every_palette_value_stays_a_colour(self):
        self.write_override()
        self.assertTrue(all(value.startswith('#') and len(value) == 7
                            for value in self.accent().values()))


class HelperTests(unittest.TestCase):
    """The helper publishes a record and a stylesheet, and can undo both."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.environment = dict(os.environ,
                                XDG_STATE_HOME=str(self.base / 'state'),
                                XDG_CONFIG_HOME=str(self.base / 'config'))
        self.record = self.base / 'state/oldbook/palette-override.json'
        self.stylesheet = self.base / 'config/waybar/waybar-accent.css'

    def run_helper(self, *arguments):
        return subprocess.run([sys.executable, str(HELPER), *arguments],
                              capture_output=True, text=True, timeout=60,
                              env=self.environment, cwd=str(REPO))

    def test_apply_writes_a_record_and_a_stylesheet(self):
        image = painting(self.base / 'nocturne.png', 'nocturne')
        result = self.run_helper('apply', '--painting', str(image))
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(self.record.read_text())
        self.assertEqual(record['theme'], 'gruvbox-dark')
        self.assertIn(record['accent'], THEME['palette'].values())
        css = self.stylesheet.read_text()
        self.assertIn('@define-color oldbook_accent ' + record['accent'], css)
        # The Ghost badge is branding, not decoration: it never appears here.
        self.assertNotIn('custom-ghost', css)

    def test_a_second_run_on_the_same_painting_does_no_work(self):
        image = painting(self.base / 'sunset.png', 'sunset')
        self.run_helper('apply', '--painting', str(image))
        again = self.run_helper('apply', '--painting', str(image))
        self.assertIn('unchanged', again.stdout)

    def test_clear_returns_the_declared_accent(self):
        image = painting(self.base / 'nocturne.png', 'nocturne')
        self.run_helper('apply', '--painting', str(image))
        result = self.run_helper('clear')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.record.exists())
        self.assertIn(THEME['palette']['yellow'], self.stylesheet.read_text())


if __name__ == '__main__':
    unittest.main()
