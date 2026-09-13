"""cue-render must reproduce the marked fragment exactly, be idempotent, and
fail loudly -- never silently -- on a missing, duplicate or out-of-order
marker, or a missing target file.
"""
import importlib.machinery
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'alpine/bin/cue-render'
CUE_DIR = REPO / 'alpine/cue/waybar'

CSS_MARKED = '''#custom-ghost:hover { background: red; }
/* BEGIN cue-generated: ghost-wander -- edit alpine/cue/waybar/ghost_wander.cue and run alpine/bin/cue-sync, not this block */
placeholder
/* END cue-generated: ghost-wander */
#workspaces { margin: 3px 5px 3px 0; }
'''

CFG_MARKED = '''    "custom/ghost": {
      "format": "{}",
      // BEGIN cue-generated: ghost-wander -- edit alpine/cue/waybar/ghost_wander.cue and run alpine/bin/cue-sync, not this block
      "placeholder": true
      // END cue-generated: ghost-wander
    },
'''

EXPECTED_CSS_FRAGMENT = '''@keyframes oldbook-ghost-wander {
    0%    { margin: 3px 5px 3px 3px; }
    12.5% { margin: 1px 5px 5px 3px; }
    25%   { margin: 0px 5px 6px 3px; }
    37.5% { margin: 1px 5px 5px 3px; }
    50%   { margin: 3px 5px 3px 3px; }
    62.5% { margin: 5px 5px 1px 3px; }
    75%   { margin: 6px 5px 0px 3px; }
    87.5% { margin: 5px 5px 1px 3px; }
    100%  { margin: 3px 5px 3px 3px; }
}
/* Jack: "make the little ghost ... float in place and wander ... like a
   tomagatchi." Small enough to read as idle rather than broken; enabled by
   oldbook-waybar-ghost-class, which only adds this class when he has not
   turned it off (ghost.json's wander key) and the power ladder still
   allows the ghost-wander effect (sheds at low battery like every other
   small ambient motion on this desktop). */
#custom-ghost.wander {
    animation: oldbook-ghost-wander 11s ease-in-out infinite;
}'''

EXPECTED_CFG_FRAGMENT = '''      "exec": "~/.local/bin/oldbook-waybar-ghost-class",
      "return-type": "json",
      "interval": 30'''


def load_helper():
    loader = importlib.machinery.SourceFileLoader('cue_render', str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@unittest.skipUnless(shutil.which('cue'), 'cue is not installed')
class CueRenderUnitTests(unittest.TestCase):
    """Tests against the real alpine/cue/waybar source: the correctness bar
    that the CUE source reproduces exactly what used to be hand-authored.
    """

    def setUp(self):
        self.module = load_helper()
        self.profiles = self.module.cue_export()

    def test_all_three_profiles_present(self):
        self.assertEqual(set(self.profiles), {'gruvbox-dark', 'catppuccin-mocha', 'monochrome-test'})

    def test_css_fragment_byte_identical_to_hand_authored_original(self):
        rendered = self.module.render_ghost_css(self.profiles['gruvbox-dark'])
        self.assertEqual(rendered, EXPECTED_CSS_FRAGMENT + '\n')

    def test_config_fragment_byte_identical_to_hand_authored_original(self):
        rendered = self.module.render_ghost_config_fragment(self.profiles['gruvbox-dark'])
        self.assertEqual(rendered, EXPECTED_CFG_FRAGMENT + '\n')

    def test_all_three_profiles_render_identically_today(self):
        rendered = {name: self.module.render_ghost_css(params)
                    for name, params in self.profiles.items()}
        self.assertEqual(len(set(rendered.values())), 1)

    def test_amplitude_override_changes_only_the_top_bottom_split(self):
        params = dict(self.profiles['gruvbox-dark'])
        params['amplitudePx'] = 6
        rendered = self.module.render_ghost_css(params)
        self.assertIn('0%    { margin: 3px 5px 3px 3px; }', rendered)  # offset 0: unaffected by amplitude
        self.assertIn('25%   { margin: -3px 5px 9px 3px; }', rendered)  # 25% peak: now +/-6 instead of +/-3


class CueRenderMarkerTests(unittest.TestCase):
    """Tests against a throwaway fixture, never the real profile files."""

    def setUp(self):
        self.module = load_helper()
        self.temporary = tempfile.TemporaryDirectory(prefix='oldbook-cue-render-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_fixture(self, css_text=CSS_MARKED, cfg_text=CFG_MARKED):
        base = self.root / 'themes/profiles/gruvbox-dark/.config/waybar'
        base.mkdir(parents=True)
        (base / 'style.css').write_text(css_text)
        (base / 'config.jsonc').write_text(cfg_text)
        return base

    def test_finds_marker_region(self):
        base = self.write_fixture()
        text = (base / 'style.css').read_text()
        begin, end = self.module.find_marker_region(text, 'ghost-wander', base / 'style.css')
        lines = text.split('\n')
        self.assertIn('BEGIN cue-generated: ghost-wander', lines[begin])
        self.assertIn('END cue-generated: ghost-wander', lines[end])

    def test_apply_render_replaces_only_the_interior(self):
        base = self.write_fixture()
        text = (base / 'style.css').read_text()
        updated = self.module.apply_render(text, 'ghost-wander', 'new content\n', base / 'style.css')
        self.assertIn('new content', updated)
        self.assertNotIn('placeholder', updated)
        self.assertIn('BEGIN cue-generated: ghost-wander', updated)
        self.assertIn('END cue-generated: ghost-wander', updated)
        # everything outside the markers is untouched
        self.assertIn('#custom-ghost:hover { background: red; }', updated)
        self.assertIn('#workspaces { margin: 3px 5px 3px 0; }', updated)

    def test_missing_begin_marker_exits_loudly(self):
        base = self.write_fixture(css_text=CSS_MARKED.replace(
            '/* BEGIN cue-generated: ghost-wander -- edit alpine/cue/waybar/ghost_wander.cue and run alpine/bin/cue-sync, not this block */\n', ''))
        text = (base / 'style.css').read_text()
        with self.assertRaises(SystemExit) as context:
            self.module.find_marker_region(text, 'ghost-wander', base / 'style.css')
        self.assertIn('no "BEGIN cue-generated: ghost-wander" marker found', str(context.exception))

    def test_missing_end_marker_exits_loudly(self):
        base = self.write_fixture(css_text=CSS_MARKED.replace(
            '/* END cue-generated: ghost-wander */\n', ''))
        text = (base / 'style.css').read_text()
        with self.assertRaises(SystemExit) as context:
            self.module.find_marker_region(text, 'ghost-wander', base / 'style.css')
        self.assertIn('no "END cue-generated: ghost-wander" marker found', str(context.exception))

    def test_duplicate_begin_marker_exits_loudly(self):
        marker = '/* BEGIN cue-generated: ghost-wander -- edit alpine/cue/waybar/ghost_wander.cue and run alpine/bin/cue-sync, not this block */\n'
        base = self.write_fixture(css_text=CSS_MARKED.replace(marker, marker + marker))
        text = (base / 'style.css').read_text()
        with self.assertRaises(SystemExit) as context:
            self.module.find_marker_region(text, 'ghost-wander', base / 'style.css')
        self.assertIn('2 "BEGIN cue-generated: ghost-wander" markers found', str(context.exception))

    def test_end_before_begin_exits_loudly(self):
        text = ('/* END cue-generated: ghost-wander */\n'
                'placeholder\n'
                '/* BEGIN cue-generated: ghost-wander -- ... */\n')
        with self.assertRaises(SystemExit) as context:
            self.module.find_marker_region(text, 'ghost-wander', Path('fixture.css'))
        self.assertIn('appears before', str(context.exception))

    def test_render_all_is_idempotent(self):
        self.write_fixture()
        original_module = self.module
        original_module.ROOT = self.root
        original_module.CUE_DIR = CUE_DIR
        original_module.targets = lambda profiles: [
            (self.root / 'themes/profiles/gruvbox-dark/.config/waybar/style.css',
             'ghost-wander', 'rendered once\n'),
            (self.root / 'themes/profiles/gruvbox-dark/.config/waybar/config.jsonc',
             'ghost-wander', '"k": "v"\n'),
        ]
        changed_first = original_module.render_all(check=False, profiles={})
        self.assertEqual(len(changed_first), 2)
        changed_second = original_module.render_all(check=False, profiles={})
        self.assertEqual(changed_second, [], 'second render must be a no-op (idempotent)')

    def test_check_mode_reports_but_does_not_write(self):
        base = self.write_fixture()
        css_path = base / 'style.css'
        before = css_path.read_text()
        self.module.ROOT = self.root
        self.module.targets = lambda profiles: [(css_path, 'ghost-wander', 'would-be-new-content\n')]
        changed = self.module.render_all(check=True, profiles={})
        self.assertEqual(changed, [css_path])
        self.assertEqual(css_path.read_text(), before, '--check must not write anything')

    def test_target_file_missing_exits_loudly(self):
        base = self.write_fixture()
        missing = base / 'does-not-exist.css'
        self.module.ROOT = self.root
        self.module.targets = lambda profiles: [(missing, 'ghost-wander', 'x')]
        with self.assertRaises(SystemExit) as context:
            self.module.render_all(check=False, profiles={})
        self.assertIn('target file does not exist', str(context.exception))

    def test_all_writes_atomic_when_one_target_has_a_bad_marker(self):
        """A corrupt marker anywhere in the batch must not leave the other,
        valid targets partially rewritten -- either everything renders, or
        nothing does.
        """
        base = self.write_fixture()
        good = base / 'style.css'
        bad = base / 'config.jsonc'
        bad.write_text('no markers here at all\n')
        good_before = good.read_text()
        self.module.ROOT = self.root
        self.module.targets = lambda profiles: [
            (good, 'ghost-wander', 'new content\n'),
            (bad, 'ghost-wander', 'new content\n'),
        ]
        with self.assertRaises(SystemExit):
            self.module.render_all(check=False, profiles={})
        self.assertEqual(good.read_text(), good_before, 'the valid target must not have been written')


if __name__ == '__main__':
    unittest.main()
