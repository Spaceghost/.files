"""The command deck reports before it offers, and offers nothing that lies.

Every test here is hermetic: HOME's own configuration, runtime and state
directories are redirected into a temporary tree, and the deck's `run`,
`launch`, `notify` and `choose` are replaced, so nothing in this file can reach
the live desktop. That is deliberate. The deck's rows write preference files
directly, and a test that ran one against the real HOME would change the
desktop under the user.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'alpine/desktop/.local/bin/oldbook-control'
HELPERS = REPO / 'alpine/desktop/.local/bin'


def load():
    loader = importlib.machinery.SourceFileLoader('oldbook_control', str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


control = load()


class DeckTestCase(unittest.TestCase):
    """A deck with nowhere real to write and nothing real to run."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='oldbook-control-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ('config', 'runtime', 'state'):
            (self.root / name).mkdir(mode=0o700)
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_RUNTIME_DIR': str(self.root / 'runtime'),
            'XDG_STATE_HOME': str(self.root / 'state'),
            'OLDBOOK_POWER_ROOT': str(self.root / 'power'),
        }).start()
        self.ran, self.launched, self.notified, self.answers = [], [], [], []
        mock.patch.object(control, 'run', self.record_run).start()
        mock.patch.object(control, 'launch', self.record_launch).start()
        mock.patch.object(control, 'notify', self.record_notify).start()
        mock.patch.object(control, 'choose', self.record_choose).start()

    def record_run(self, args, **kwargs):
        self.ran.append([str(argument) for argument in args])
        return types.SimpleNamespace(returncode=1, stdout='', stderr='')

    def record_launch(self, args):
        self.launched.append([str(argument) for argument in args])

    def record_notify(self, title, body):
        self.notified.append((title, body))

    def record_choose(self, title, options, lines=18):
        self.headings = getattr(self, 'headings', [])
        self.headings.append(title)
        self.offered = list(options)
        return self.answers.pop(0) if self.answers else ''

    def supplies(self, mains=True, capacity=86):
        """A synthetic power tree, so the posture never depends on this machine."""
        root = self.root / 'power'
        (root / 'AC').mkdir(parents=True)
        (root / 'AC/type').write_text('Mains\n')
        (root / 'AC/online').write_text('1\n' if mains else '0\n')
        (root / 'BAT0').mkdir(parents=True)
        (root / 'BAT0/type').write_text('Battery\n')
        (root / 'BAT0/status').write_text('Charging\n' if mains else 'Discharging\n')
        (root / 'BAT0/capacity').write_text(f'{capacity}\n')

    def rows(self, section='main'):
        return control.deck(section)


class RowTests(DeckTestCase):
    def test_every_row_is_a_label_and_something_to_do_or_a_rule(self):
        for section in ('main', 'network'):
            rows = self.rows(section)
            self.assertTrue(rows)
            for label, action in rows:
                self.assertIsInstance(label, str)
                self.assertTrue(label.strip(), 'a row must have a visible label')
                self.assertTrue(action is None or callable(action))

    def test_labels_are_unique_so_no_row_shadows_another(self):
        for section in ('main', 'network'):
            labels = [label for label, _ in self.rows(section)]
            self.assertEqual(len(labels), len(set(labels)))

    def test_only_section_rules_are_inert(self):
        inert = [label for label, action in self.rows() if action is None]
        self.assertTrue(inert, 'the deck is grouped, so it has rules')
        for label in inert:
            self.assertTrue(label.startswith('──'))

    def test_picking_a_rule_draws_the_deck_again_and_runs_nothing(self):
        rule = next(label for label, action in self.rows() if action is None)
        self.answers = [rule, '']
        control.menu('main')
        self.assertEqual(self.ran, [])
        self.assertEqual(self.launched, [])
        self.assertEqual(len(self.headings), 2, 'the deck redraws itself')

    def test_the_deck_keeps_every_action_the_rice_catalogue_names(self):
        labels = ' '.join(label for label, _ in self.rows())
        for promised in ('Applications', 'Expo', 'Switch window', 'Bottom decoration',
                         'Artwork gallery', 'YouTube', 'Video background', 'Ghostty',
                         'Reactor', 'Transmissions', 'Sound studio', 'Keyboard glow',
                         'Night light', 'Ambient screen', 'Sound cues', 'Now transmitting',
                         'Application firewall', 'Notifications', 'Edit the Ghost Planet',
                         'Session', 'Help'):
            self.assertIn(promised, labels)

    def test_no_row_is_wider_than_the_menu_it_is_drawn_in(self):
        """Fuzzel is opened at 62 columns; a wider row would be cut off."""
        for section in ('main', 'network'):
            for label, _ in self.rows(section):
                self.assertLessEqual(control.columns(label), 62, label)

    def test_a_shortcut_hint_starts_at_the_same_column_on_every_row(self):
        hinted = [label for label, _ in self.rows() if 'Super+' in label]
        self.assertGreater(len(hinted), 3)
        starts = {control.columns(label[:label.index('Super+')]) for label in hinted}
        self.assertEqual(len(starts), 1, hinted)

    def test_an_icon_is_measured_as_the_two_columns_it_draws(self):
        self.assertEqual(control.columns('󰊠'), 2)
        self.assertEqual(control.columns('ab'), 2)
        self.assertEqual(control.columns('󰊠  Applications'), 4 + len('Applications'))

    def test_a_shortcut_hint_is_only_claimed_where_sway_binds_one(self):
        """Every Super+… the deck advertises must be a binding the config has."""
        config = (REPO / 'alpine/desktop/.config/sway')
        bindings = '\n'.join(path.read_text() for path in
                             [config / 'config', config / 'gestures.conf',
                              *(config / 'local.d').glob('*.conf')])
        self.answers = ['']
        control.power()
        labels = [label for label, _ in self.rows()] + self.offered
        claimed = set(re.findall(r'(Super\+[A-Za-z+]+)', ' '.join(labels)))
        self.assertTrue(claimed)
        for hint in claimed:
            key = hint.replace('Super+', '').replace('Enter', 'Return')
            pattern = r'bindsym\s+(\$mod|Mod4)\+' + re.escape(key).replace(
                r'\+', r'\+') + r'\b'
            self.assertRegex(bindings, re.compile(pattern, re.IGNORECASE),
                             f'{hint} is advertised but not bound')

    def test_the_deck_offers_what_the_desktop_has_grown(self):
        labels = ' '.join(label for label, _ in self.rows())
        for arrival in ('Theme', 'Power posture', 'Watch mode', 'Bed mode', 'rice'):
            self.assertIn(arrival, labels)


class NoBreathingPaintingTests(DeckTestCase):
    """The painting never breathes, and no row here can change that."""

    def test_the_written_preference_always_holds_the_painting_still(self):
        for wanted in (True, False, 1, 0, 'yes', None):
            self.assertIs(control.breath_preferences(wanted)['wallpaper'], False)

    def test_the_caption_is_the_only_half_the_deck_switches(self):
        self.assertIs(control.BREATH_WALLPAPER, False)
        self.assertTrue(control.breath_preferences(True)['caption'])
        self.assertFalse(control.breath_preferences(False)['caption'])

    def test_switching_the_caption_never_offers_the_painting(self):
        written = []
        air = types.ModuleType('air')
        air.read_preferences = lambda: {'wallpaper': False, 'caption': False}
        air.write_preferences = written.append
        with mock.patch.dict('sys.modules', {'air': air}):
            control.caption_breath()
        self.assertEqual(written, [{'wallpaper': False, 'caption': True}])
        self.assertEqual(self.ran[0][:1], ['notify-send'])
        self.assertNotIn('painting', ' '.join(self.ran[0]).lower())

    def test_no_row_mentions_a_breathing_painting(self):
        for label, _ in self.rows():
            self.assertNotRegex(label.lower(), r'painting.*(breath|swell)')

    def test_the_source_writes_no_other_breath_preference(self):
        text = SOURCE.read_text()
        self.assertEqual(text.count('write_preferences'), 1)
        self.assertIn('"wallpaper": BREATH_WALLPAPER', text)


class StateTests(DeckTestCase):
    def test_a_switch_says_which_way_it_is_set(self):
        self.assertIn(control.ON, control.switch('x', 'Name', True, 'on', 'off'))
        self.assertIn(control.OFF, control.switch('x', 'Name', False, 'on', 'off'))

    def test_an_unreadable_switch_claims_nothing(self):
        label = control.switch('x', 'Name', None, 'on', 'off')
        self.assertNotIn(control.ON, label)
        self.assertNotIn(control.OFF, label)
        self.assertIn('Name', label)

    def test_switches_read_the_desktops_own_preference_files(self):
        config = self.root / 'config/oldbook'
        config.mkdir(parents=True)
        (config / 'sound.json').write_text(json.dumps({'enabled': False}))
        (config / 'osd.json').write_text(json.dumps({'card': False}))
        (config / 'ambient-display.json').write_text(json.dumps({'enabled': True}))
        state = control.switches({'posture': 'mains'})
        self.assertIs(state['cues'], False)
        self.assertIs(state['card'], False)
        self.assertIs(state['ambient'], True)

    def test_the_night_light_needs_a_location_before_it_claims_anything(self):
        self.assertEqual(control.night_light(), 'unconfigured')
        config = self.root / 'config/oldbook'
        config.mkdir(parents=True)
        (config / 'location.json').write_text('{}')
        self.assertIs(control.night_light(), False)
        self.assertEqual(self.ran[-1][:1], ['pgrep'])

    def test_the_prompt_names_the_posture_and_the_charge(self):
        self.assertEqual(control.power_summary({'posture': 'battery-low',
                                                'capacity': 18, 'shed': ['blur']}),
                         'BATTERY LOW 18% · SHEDDING 1')
        self.assertEqual(control.power_summary({'posture': 'mains', 'capacity': 86}),
                         'MAINS 86%')
        self.assertEqual(control.power_summary(None), '')

    def test_the_deck_heads_itself_with_the_posture(self):
        self.supplies(mains=True, capacity=86)
        self.answers = ['']
        control.menu('main')
        self.assertIn('SPACE GHOST · CONTROL DECK', self.headings[0])
        self.assertIn('MAINS 86%', self.headings[0])

    def test_an_unregistered_ladder_entry_leaves_the_state_readable(self):
        control.library()
        import power_source
        self.assertNotIn(control.LADDER_EFFECT, power_source.LADDER)
        for name in power_source.POSTURES:
            self.assertTrue(control.detailed({'posture': name}))

    def test_a_registered_ladder_entry_sheds_the_state_but_not_the_posture(self):
        control.library()
        import power_source
        with mock.patch.dict(power_source.LADDER,
                             {control.LADDER_EFFECT: 'battery-low'}):
            self.assertTrue(control.detailed({'posture': 'battery'}))
            self.assertFalse(control.detailed({'posture': 'battery-critical'}))
            shed = control.switches({'posture': 'battery-critical'})
        self.assertEqual(set(shed.values()), {None})
        self.supplies(mains=False, capacity=6)
        self.assertEqual(control.power_summary(control.posture()).split()[0], 'BATTERY')

    def test_state_reading_never_reaches_the_users_own_home(self):
        home = self.root / 'config/oldbook'
        home.mkdir(parents=True)
        control.switches({'posture': 'mains'})
        self.assertEqual(control.config('sound.json').parent, home)


class HelperTests(DeckTestCase):
    """Every helper the deck names must be one this repository actually ships."""

    def test_named_helpers_exist_in_the_checkout(self):
        named = set(re.findall(r'BIN / "(oldbook-[a-z-]+)"', SOURCE.read_text()))
        self.assertTrue(named)
        for name in sorted(named):
            self.assertTrue((HELPERS / name).is_file(), f'{name} is not shipped')

    def names(self, helper, word):
        """Whether a helper's own source still spells this word, in either quote."""
        source = (HELPERS / helper).read_text()
        return f"'{word}'" in source or f'"{word}"' in source

    def test_literal_helper_arguments_are_ones_the_helper_still_takes(self):
        """A word the deck spells out must still be a word the helper answers to."""
        found = re.findall(r'BIN / "(oldbook-[a-z-]+)", "([a-z][a-z-]*)"',
                           SOURCE.read_text())
        self.assertTrue(found)
        for helper, argument in found:
            self.assertTrue(self.names(helper, argument),
                            f'{helper} no longer names {argument}')

    def test_arguments_the_deck_chooses_at_run_time_are_still_accepted(self):
        """The words that reach a helper through a variable, checked by hand.

        The scan above cannot see these, and they are exactly the ones that go
        stale when a helper's vocabulary changes underneath the deck.
        """
        expected = {
            'oldbook-keyboard-backlight': ('status', 'ambient', 'breathe',
                                           'breathe-air', 'typing', 'typing-dark',
                                           'typing-wpm', 'typing-dark-wpm',
                                           'steady', 'up', 'down', 'toggle'),
            'oldbook-ambient-display': ('status', 'on', 'off'),
            'oldbook-power-mode': ('override', 'show', 'ladder'),
            'oldbook-watch': ('start', 'stop'),
            'oldbook-cat': ('status', 'on', 'off', 'stop', 'interactions', 'fans'),
            'oldbook-theme': ('use', 'create'),
            'oldbook-rice': ('list',),
        }
        for helper, arguments in expected.items():
            for argument in arguments:
                self.assertTrue(self.names(helper, argument),
                                f'{helper} no longer names {argument}')

    def test_the_posture_menu_offers_exactly_the_postures_that_exist(self):
        control.library()
        import power_source
        self.supplies()
        self.answers = ['']
        control.power_posture()
        offered = ' '.join(self.offered)
        for name in power_source.POSTURES:
            self.assertIn(name.replace('-', ' '), offered)

    def test_documents_the_deck_opens_are_in_the_checkout(self):
        for relative in re.findall(r'REPO / "(alpine/[^"]+)"', SOURCE.read_text()):
            if relative.endswith('.md'):
                self.assertTrue((REPO / relative).is_file(), relative)

    def test_the_repository_anchor_is_the_one_the_replay_rewrites(self):
        self.assertIn('REPO = Path(__file__).resolve().parents[4]', SOURCE.read_text())

    def test_every_direct_action_is_reachable_and_named_in_the_usage(self):
        for name, action in control.DIRECT.items():
            self.assertTrue(callable(action), name)
        for name in control.REPORTS:
            self.assertIn(name, control.DIRECT)


class SubmenuTests(DeckTestCase):
    def test_the_theme_menu_switches_through_the_shared_helper(self):
        catalogue = [{'id': 'gruvbox-dark', 'name': 'Gruvbox Dark'},
                     {'id': 'catppuccin-mocha', 'name': 'Catppuccin Mocha'}]
        with mock.patch.object(control, 'themes',
                               lambda: ('gruvbox-dark', catalogue)):
            self.answers = [f'{control.UNPICKED}  Catppuccin Mocha']
            control.theme()
        self.assertEqual(self.launched,
                         [[str(control.BIN / 'oldbook-theme'), 'use',
                           'catppuccin-mocha', '--notify']])
        self.assertIn('GRUVBOX DARK', self.headings[0])

    def test_the_theme_menu_marks_the_active_theme_and_offers_a_repair(self):
        catalogue = [{'id': 'gruvbox-dark', 'name': 'Gruvbox Dark'}]
        with mock.patch.object(control, 'themes',
                               lambda: ('gruvbox-dark', catalogue)):
            self.answers = ['']
            control.theme()
        active = next(label for label in self.offered if 'Gruvbox' in label)
        self.assertTrue(active.startswith(control.PICKED))
        self.assertIn('reapply', active)

    def test_an_unreadable_catalogue_says_so_instead_of_offering_nothing(self):
        with mock.patch.object(control, 'themes', lambda: (None, [])):
            control.theme()
        self.assertEqual(self.launched, [])
        self.assertEqual(self.notified[0][0], 'Desktop theme')

    def catalogue(self):
        return mock.patch.object(control, 'themes', lambda: (
            'gruvbox-dark', [{'id': 'gruvbox-dark', 'name': 'Gruvbox Dark'}]))

    def test_a_new_theme_is_described_right_here_and_handed_to_the_theme_command(self):
        """Jack: "I want to select the option to make a new theme and just type
        there, not go to the wallpaper section." The description is typed in
        the deck's own prompt and reaches the theme command as one literal
        argument; no painting is asked for anywhere on the way."""
        phrase = 'moonlit library; $(touch /tmp/never)'
        with self.catalogue(), mock.patch.object(control, 'ask', return_value=phrase) as ask:
            self.answers = [control.DESCRIBE_THEME]
            control.theme()
        ask.assert_called_once()
        self.assertIn('Describe', ask.call_args.args[0])
        self.assertEqual(self.launched, [[str(control.BIN / 'oldbook-theme'), 'create',
                                          phrase, '--notify']])
        self.assertFalse(any('Paint a new' in row or 'workshop' in row for row in self.offered),
                         'the gallery is no longer the way to a theme')

    def test_backing_out_of_the_description_creates_nothing(self):
        with self.catalogue(), mock.patch.object(control, 'ask', return_value=None):
            self.answers = [control.DESCRIBE_THEME]
            control.theme()
        self.assertEqual(self.launched, [])

    def test_a_surprise_theme_needs_no_description(self):
        with self.catalogue():
            self.answers = [control.SURPRISE_THEME]
            control.theme()
        self.assertEqual(self.launched, [[str(control.BIN / 'oldbook-theme'), 'create',
                                          '--random', '--notify']])

    def test_the_gallery_row_opens_the_gallery_and_nothing_else(self):
        with self.catalogue():
            self.answers = [control.GALLERY]
            control.theme()
        self.assertEqual(self.launched, [[str(control.BIN / 'oldbook-wallpaper'), 'pick']])

    def test_the_theme_menu_lists_the_catalogue_before_its_own_rows(self):
        with self.catalogue():
            self.answers = ['']
            control.theme()
        self.assertEqual(self.offered[-3:], [control.DESCRIBE_THEME, control.SURPRISE_THEME,
                                             control.GALLERY])
        self.assertTrue(self.offered[0].endswith('Gruvbox Dark · reapply across the desktop'))

    def test_a_description_is_typed_into_the_launcher_with_no_rows(self):
        answered = []

        def run(args, **kwargs):
            answered.append(([str(argument) for argument in args], kwargs))
            return types.SimpleNamespace(returncode=0, stdout='  moon   books \n', stderr='')

        with mock.patch.object(control, 'run', run):
            self.assertEqual(control.ask('Describe the new theme'), 'moon books')
        command, kwargs = answered[0]
        self.assertEqual(command[-2:], ['--lines', '0'])
        self.assertEqual(kwargs.get('input'), '')
        self.assertIn('Describe the new theme', ' '.join(command))
        # Escape, or Enter on nothing, is no answer at all.
        with mock.patch.object(control, 'run', lambda *a, **k: types.SimpleNamespace(
                returncode=1, stdout='typed then escaped', stderr='')):
            self.assertIsNone(control.ask('Describe the new theme'))
        with mock.patch.object(control, 'run', lambda *a, **k: types.SimpleNamespace(
                returncode=0, stdout='   \n', stderr='')):
            self.assertIsNone(control.ask('Describe the new theme'))

    def test_the_posture_menu_hands_the_decision_back(self):
        self.supplies(mains=True, capacity=86)
        self.answers = [f'{control.PICKED}  Automatic · follow the batteries, '
                        'reading mains now']
        control.power_posture()
        self.assertEqual(self.ran[-1],
                         [str(control.BIN / 'oldbook-power-mode'), 'override', 'auto'])

    def test_the_posture_menu_can_hold_one_by_hand(self):
        self.supplies(mains=True, capacity=86)
        self.answers = [f'{control.UNPICKED}  Hold battery low']
        control.power_posture()
        self.assertEqual(self.ran[-1][-2:], ['override', 'battery-low'])

    def test_watch_mode_says_how_to_leave_before_it_is_engaged(self):
        self.answers = ['󰈈  Engage · the keyboard stops answering']
        control.watch()
        self.assertIn('SUPER + SHIFT + ESCAPE', self.headings[0])
        self.assertEqual(self.launched,
                         [[str(control.BIN / 'oldbook-watch'), 'start']])

    def test_declining_watch_mode_engages_nothing(self):
        self.answers = ['←  Not now']
        control.watch()
        self.assertEqual(self.launched, [])
        self.assertEqual(self.ran, [])

    def test_bed_mode_reports_before_it_offers(self):
        with mock.patch.object(control, 'probe', lambda *_: {
                'enabled': True, 'record': {'bed': {'running': True}}}), \
                mock.patch.object(control.shutil, 'which', lambda _: '/x'):
            self.answers = ['󰄛  She is abed · give the fans back now']
            control.cat()
        self.assertIn('SHE IS ABED', self.headings[0])
        self.assertEqual(self.launched, [[str(control.BIN / 'oldbook-cat'), 'stop']])

    def test_bed_mode_says_so_when_the_helper_is_not_installed_yet(self):
        with mock.patch.object(control, 'probe', lambda *_: None), \
                mock.patch.object(control.shutil, 'which', lambda _: None):
            control.cat()
        self.assertEqual(self.notified[0][0], 'Bed mode')
        self.assertEqual(self.launched, [])

    def test_the_rice_menu_describes_an_entry_and_runs_nothing(self):
        config = self.root / 'config/oldbook'
        config.mkdir(parents=True)
        (config / 'rice.json').write_text(json.dumps({'version': 1, 'entries': [
            {'id': 'bed-mode', 'title': 'Bed mode', 'date': '2026-09-09',
             'summary': 'She lies on it.', 'trigger': 'Lock the session',
             'run': ['rm', '-rf', 'everything']}]}))
        self.answers = [f'{control.UNPICKED}  9 Sep  Bed mode']
        control.rice()
        self.assertEqual(self.launched, [])
        self.assertEqual(self.ran, [])
        self.assertEqual(self.notified[0][0], 'Bed mode')
        self.assertIn('Lock the session', self.notified[0][1])

    def test_the_rice_menu_can_open_the_whole_list_in_a_terminal(self):
        config = self.root / 'config/oldbook'
        config.mkdir(parents=True)
        (config / 'rice.json').write_text(json.dumps({'version': 1, 'entries': [
            {'id': 'bed-mode', 'title': 'Bed mode', 'date': '2026-09-09',
             'summary': 'She lies on it.', 'trigger': 'Lock the session'}]}))
        self.answers = ['󰋖  The whole list, in a terminal']
        control.rice()
        self.assertEqual(self.launched[0][:1], ['foot'])
        self.assertEqual(self.launched[0][-1], 'rice-report')

    def test_a_report_terminal_runs_this_deck_and_never_a_shell(self):
        control.terminal('Power Posture', 'power-report')
        self.assertNotIn('sh', self.launched[0])
        self.assertEqual(self.launched[0][-2:],
                         [str(control.BIN / 'oldbook-control'), 'power-report'])


class TrackCardTests(DeckTestCase):
    def test_the_card_switch_writes_only_into_the_redirected_config(self):
        control.track_card()
        written = json.loads((self.root / 'config/oldbook/osd.json').read_text())
        self.assertIs(written['card'], False)
        control.track_card()
        written = json.loads((self.root / 'config/oldbook/osd.json').read_text())
        self.assertIs(written['card'], True)

    def test_the_card_switch_keeps_the_rest_of_the_osd_settings(self):
        config = self.root / 'config/oldbook'
        config.mkdir(parents=True)
        (config / 'osd.json').write_text(json.dumps({'card': True, 'pill': False}))
        control.track_card()
        written = json.loads((config / 'osd.json').read_text())
        self.assertEqual(written, {'card': False, 'pill': False})


class WindowTests(DeckTestCase):
    def test_a_window_without_an_app_id_is_still_switchable(self):
        tree = {'type': 'root', 'nodes': [{'type': 'workspace', 'name': '1', 'nodes': [
            {'id': 7, 'name': 'Firefox', 'window_properties': {'class': 'firefox'}},
            {'id': 8, 'name': 'Foot', 'window_properties': None}]}]}
        with mock.patch.object(control, 'run', lambda *a, **k: types.SimpleNamespace(
                returncode=0, stdout=json.dumps(tree))):
            self.answers = ['']
            control.windows()
        self.assertEqual(len(self.offered), 1)
        self.assertIn('firefox', self.offered[0])


if __name__ == '__main__':
    unittest.main()


class FirewallSwitchTests(DeckTestCase):
    """The one switch on this deck that can leave the machine worse off.

    Every other row here changes how the desktop looks. This one decides whether
    applications may reach the network without asking, so it is tested for two
    things the others are not: that reading it costs nothing, and that it cannot
    be thrown off by a single stray keystroke.
    """

    def setUp(self):
        super().setUp()
        self.initd = self.root / 'init.d'
        self.initd.mkdir()
        (self.initd / control.FIREWALL_SERVICE).write_text('#!/sbin/openrc-run\n')
        self.started = self.root / 'openrc/started'
        self.started.mkdir(parents=True)
        mock.patch.dict(os.environ, {
            'OLDBOOK_INITD_ROOT': str(self.initd),
            'OLDBOOK_OPENRC_ROOT': str(self.root / 'openrc'),
        }).start()

    def bring_up(self):
        (self.started / control.FIREWALL_SERVICE).symlink_to(
            self.initd / control.FIREWALL_SERVICE)

    def test_the_state_is_read_from_a_file_and_runs_nothing(self):
        self.assertIs(control.firewall_running(), False)
        self.bring_up()
        self.assertIs(control.firewall_running(), True)
        self.assertEqual(self.ran, [], 'drawing the deck must not shell out')

    def test_a_machine_without_the_service_claims_nothing(self):
        (self.initd / control.FIREWALL_SERVICE).unlink()
        self.assertIsNone(control.firewall_running())

    def test_the_row_says_which_way_it_is_set_before_it_is_thrown(self):
        self.supplies()
        self.bring_up()
        label = next(text for text, _ in self.rows() if 'Application firewall' in text)
        self.assertIn(control.ON, label)
        self.assertIn('ask first', label)
        (self.started / control.FIREWALL_SERVICE).unlink()
        label = next(text for text, _ in self.rows() if 'Application firewall' in text)
        self.assertIn(control.OFF, label)
        self.assertIn('connect freely', label)

    def test_lowering_it_asks_first_and_a_refusal_changes_nothing(self):
        self.bring_up()
        self.answers = ['']                      # dismissed
        control.firewall_toggle()
        self.assertEqual(self.ran, [], 'a dismissed prompt must not stop the daemon')
        self.answers = [f'{control.OFF}  Leave it filtering']
        control.firewall_toggle()
        self.assertEqual(self.ran, [])
        self.assertIn('LOWER THE FIREWALL?', self.headings)

    def test_confirming_stops_it_through_doas(self):
        self.bring_up()
        self.answers = [f'{control.ON}  Stop it · applications connect freely']
        control.firewall_toggle()
        self.assertEqual(self.ran, [['doas', '-n', 'rc-service',
                                     control.FIREWALL_SERVICE, 'stop']])

    def test_raising_it_again_does_not_ask(self):
        self.answers = []                        # nothing to answer with
        control.firewall_toggle()
        self.assertEqual(self.ran, [['doas', '-n', 'rc-service',
                                     control.FIREWALL_SERVICE, 'start']])
        self.assertNotIn('LOWER THE FIREWALL?', getattr(self, 'headings', []))

    def test_an_unreadable_service_is_reported_and_left_alone(self):
        (self.initd / control.FIREWALL_SERVICE).unlink()
        control.firewall_toggle()
        self.assertEqual(self.ran, [])
        self.assertTrue(any('could not be read' in body for _, body in self.notified))

    def test_a_refused_doas_says_so_rather_than_claiming_success(self):
        self.answers = []
        control.firewall_toggle()
        self.assertTrue(self.notified)
        title, body = self.notified[-1]
        self.assertEqual(title, 'Application firewall')
        self.assertIn('could not be', body,
                      'the stub returns a failure, so the deck must not claim it worked')

    def test_the_window_and_the_switch_are_separate_rows(self):
        rows = dict(self.rows('network'))
        switches = [text for text in rows if 'Application firewall' in text]
        windows = [text for text in rows if 'OpenSnitch window' in text]
        self.assertEqual(len(switches), 1)
        self.assertEqual(len(windows), 1)
        self.assertIs(rows[switches[0]], control.firewall_toggle)
        self.assertIs(rows[windows[0]], control.firewall)

    def test_the_toggle_is_bindable_on_its_own(self):
        self.assertIs(control.DIRECT['firewall-toggle'], control.firewall_toggle)
        self.assertIs(control.DIRECT['firewall'], control.firewall)
