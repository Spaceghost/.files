"""Behavior tests for contextual shortcut discovery."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


LIB = Path(__file__).resolve().parents[1] / 'desktop/.local/lib'
sys.path.insert(0, str(LIB))

from mbp_intel.shortcut_sources import ShortcutProvider


def focused_tree(app_id='firefox', pid=200, output='eDP-1'):
    return {
        'id': 1,
        'type': 'root',
        'nodes': [{
            'id': 2,
            'type': 'output',
            'name': output,
            'nodes': [{
                'id': 3,
                'type': 'workspace',
                'nodes': [{
                    'id': 4,
                    'type': 'con',
                    'focused': True,
                    'app_id': app_id,
                    'pid': pid,
                    'name': 'Private title that must not become the app name',
                    'window_properties': {},
                    'nodes': [],
                    'floating_nodes': [],
                }],
                'floating_nodes': [],
            }],
            'floating_nodes': [],
        }],
        'floating_nodes': [],
    }


class FixtureProvider(ShortcutProvider):
    def __init__(self, replies, commands=None, processes=None, profiles_path=None):
        super().__init__('/tmp/fake-sway.sock', profiles_path=profiles_path)
        self.replies = replies
        self.commands = commands or {}
        self.processes = processes or {}

    def _sway_request(self, message_type):
        result = self.replies[message_type]
        if isinstance(result, Exception):
            raise result
        return result

    def _run_command(self, argv):
        return self.commands.get(tuple(argv), '')

    def _process_snapshot(self):
        return self.processes


class ShortcutProviderTests(unittest.TestCase):
    def replies(self, config='', mode='default', tree=None,
                config_path='/tmp/mbp-intel-test-sway.conf'):
        return {
            ShortcutProvider.GET_TREE: tree or focused_tree(),
            ShortcutProvider.GET_CONFIG: {'config': config},
            ShortcutProvider.GET_BINDING_STATE: {'name': mode},
            ShortcutProvider.GET_VERSION: {'loaded_config_file_name': config_path},
        }

    def test_default_mode_expands_variables_and_honors_overrides_unbinds_options_and_groups(self):
        config = r'''
set $mod Mod4
bindsym $mod+x exec first
bindsym $mod+x exec final
bindsym --release $mod+y exec on-release
unbindsym --release $mod+y
bindcode --locked 42 exec literal --unknown
bindsym {
    $mod+Return exec foot
    --no-repeat $mod+q kill
}
mode "resize" {
    bindsym h resize shrink width 10 px
}
'''
        snapshot = FixtureProvider(self.replies(config)).snapshot()

        self.assertEqual(snapshot['app'], 'Firefox')
        self.assertEqual(snapshot['output'], 'eDP-1')
        self.assertEqual([section['title'] for section in snapshot['sections'][:2]], [
            'Firefox shortcuts', 'Sway — default',
        ])
        sway = snapshot['sections'][1]
        self.assertEqual(
            sway['coverage'],
            'Loaded main config · active mode')
        rows = {row['key']: row['description'] for row in sway['rows']}
        self.assertEqual(rows['Super+X'], 'exec final')
        self.assertNotIn('Super+Y', rows)
        self.assertEqual(rows['code 42'], 'exec literal --unknown')
        self.assertEqual(rows['Super+Enter'], 'Open terminal')
        self.assertEqual(rows['Super+Q'], 'Close focused window')
        self.assertNotIn('H', rows)

    def test_only_the_active_sway_mode_is_shown(self):
        config = '''
bindsym Mod4+x kill
mode "resize" {
    bindsym h resize shrink width 10 px
    bindsym h resize grow width 20 px
    bindsym Escape mode "default"
}
'''
        snapshot = FixtureProvider(self.replies(config, mode='resize')).snapshot()

        sway = snapshot['sections'][1]
        self.assertEqual(sway['title'], 'Sway — resize')
        self.assertEqual(sway['rows'], [
            {'key': 'H', 'description': 'Grow width by 20 px'},
            {'key': 'Escape', 'description': 'Return to default mode'},
        ])

    def test_variable_redefinition_changes_only_later_bindings(self):
        config = '''
set $mod Mod4
bindsym $mod+x exec super-action
set $mod Mod1
bindsym $mod+x exec alt-action
'''
        snapshot = FixtureProvider(self.replies(config)).snapshot()

        rows = snapshot['sections'][1]['rows']
        self.assertEqual(rows, [
            {'key': 'Super+X', 'description': 'exec super-action'},
            {'key': 'Alt+X', 'description': 'exec alt-action'},
        ])

    def test_current_nested_includes_apply_in_place_with_variables_globs_and_cycles(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-sway-includes-') as temp:
            root = Path(temp)
            main = root / 'config'
            fragments = root / 'local.d'
            fragments.mkdir()
            main_config = '''
set $parts local.d
bindsym F12 exec from-main
include $parts/*.conf
'''
            fragments.joinpath('10-first.conf').write_text(
                'unbindsym F12\nbindsym F11 exec from-include\n'
                'include nested.conf\n', encoding='utf-8')
            fragments.joinpath('nested.conf').write_text(
                'bindsym F10 exec nested\ninclude 10-first.conf\n', encoding='utf-8')
            snapshot = FixtureProvider(self.replies(
                main_config, config_path=str(main))).snapshot()

        sway = snapshot['sections'][1]
        rows = {row['key']: row['description'] for row in sway['rows']}
        self.assertNotIn('F12', rows)
        self.assertEqual(rows['F11'], 'exec from-include')
        self.assertEqual(rows['F10'], 'exec nested')
        self.assertEqual(
            sway['coverage'],
            'Loaded main config + current included files · active mode; reload after edits')

    def test_home_include_is_expanded_without_running_shell_syntax(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-sway-home-') as temp:
            home = Path(temp)
            home.joinpath('safe.conf').write_text(
                'bindsym F9 exec home-file\n', encoding='utf-8')
            marker = home / 'must-not-exist'
            config = 'include ~/safe.conf\ninclude $(touch ' + str(marker) + ')\n'
            with mock.patch.dict(os.environ, {'HOME': str(home)}):
                snapshot = FixtureProvider(self.replies(
                    config, config_path=str(home / 'config'))).snapshot()

        rows = snapshot['sections'][1]['rows']
        self.assertIn({'key': 'F9', 'description': 'exec home-file'}, rows)
        self.assertFalse(marker.exists())

    def test_redefined_include_variable_selects_the_later_file(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-sway-redefined-') as temp:
            root = Path(temp)
            root.joinpath('first.conf').write_text(
                'bindsym F8 exec first-file\n', encoding='utf-8')
            root.joinpath('second.conf').write_text(
                'bindsym F7 exec second-file\n', encoding='utf-8')
            config = '''
set $inc first.conf
include $inc
set $inc second.conf
include $inc
'''
            snapshot = FixtureProvider(self.replies(
                config, config_path=str(root / 'config'))).snapshot()

        self.assertEqual(snapshot['sections'][1]['rows'], [
            {'key': 'F8', 'description': 'exec first-file'},
            {'key': 'F7', 'description': 'exec second-file'},
        ])

    def test_canonical_include_is_loaded_only_once_across_sibling_directives(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-sway-include-once-') as temp:
            root = Path(temp)
            shared = root / 'shared.conf'
            shared.write_text('bindsym F6 exec shared-file\n', encoding='utf-8')
            config = '''
include shared.conf
unbindsym F6
include ./shared.conf
'''
            snapshot = FixtureProvider(self.replies(
                config, config_path=str(root / 'config'))).snapshot()

        self.assertNotIn('F6', {
            row['key'] for row in snapshot['sections'][1]['rows']})

    def test_modifier_order_is_normalized_for_override_but_key_case_is_distinct(self):
        config = '''
bindsym Mod4+Shift+x exec first
bindsym Shift+Mod4+x exec replacement
bindsym Mod4+Shift+X exec uppercase-keysym
'''
        snapshot = FixtureProvider(self.replies(config)).snapshot()

        descriptions = [row['description'] for row in snapshot['sections'][1]['rows']]
        self.assertEqual(descriptions, ['exec replacement', 'exec uppercase-keysym'])

    def test_configured_mbp_intel_helpers_receive_readable_labels(self):
        config = '''
bindsym Mod4+g exec ~/.local/bin/mbp-intel-wallpaper pick
bindsym Mod4+Right exec ~/.local/bin/mbp-intel-wallpaper next
bindsym Mod4+Left exec ~/.local/bin/mbp-intel-wallpaper prev
bindsym Mod4+p exec ~/.local/bin/mbp-intel-wallpaper pause
bindsym Mod4+i exec ~/.local/bin/mbp-intel-workspaces ai-next
bindsym Mod4+m exec ~/.local/bin/mbp-intel-workspaces ai-menu
bindsym Mod4+n exec swaync-client -t
bindsym Print exec ~/.local/bin/mbp-intel-screenshot full
bindsym Shift+Print exec ~/.local/bin/mbp-intel-screenshot area
bindsym Ctrl+Print exec ~/.local/bin/mbp-intel-screenshot window
bindsym XF86AudioRaiseVolume exec ~/.local/bin/mbp-intel-audio up
bindsym XF86AudioLowerVolume exec ~/.local/bin/mbp-intel-audio down
bindsym XF86AudioMute exec ~/.local/bin/mbp-intel-audio mute
bindsym XF86AudioMicMute exec ~/.local/bin/mbp-intel-audio mic-mute
bindsym XF86MonBrightnessUp exec ~/.local/bin/mbp-intel-brightness up
bindsym XF86MonBrightnessDown exec ~/.local/bin/mbp-intel-brightness down
bindsym Mod4+e exec swaynag -t warning -m "Leave?" -B "Log out" "swaymsg exit"
'''
        snapshot = FixtureProvider(self.replies(config)).snapshot()

        descriptions = {
            row['key']: row['description'] for row in snapshot['sections'][1]['rows']
        }
        self.assertEqual(descriptions, {
            'Super+G': 'Choose wallpaper',
            'Super+Right': 'Next wallpaper',
            'Super+Left': 'Previous wallpaper',
            'Super+P': 'Pause or resume wallpaper rotation',
            'Super+I': 'Focus next AI workspace',
            'Super+M': 'Choose AI workspace',
            'Super+N': 'Toggle notification center',
            'Print': 'Capture full screen',
            'Shift+Print': 'Capture selected area',
            'Ctrl+Print': 'Capture focused window',
            'XF86AudioRaiseVolume': 'Increase volume',
            'XF86AudioLowerVolume': 'Decrease volume',
            'XF86AudioMute': 'Toggle audio mute',
            'XF86AudioMicMute': 'Toggle microphone mute',
            'XF86MonBrightnessUp': 'Increase brightness',
            'XF86MonBrightnessDown': 'Decrease brightness',
            'Super+E': 'Open logout confirmation',
        })

    def test_mouse_region_options_and_xkb_groups_remain_distinct(self):
        config = '''
bindsym --border button1 exec border-action
bindsym button1 exec title-action
unbindsym --border button1
bindsym --locked Group2+Mod4+x exec grouped-action
'''
        snapshot = FixtureProvider(self.replies(config)).snapshot()

        self.assertEqual(snapshot['sections'][1]['rows'], [
            {'key': 'button1', 'description': 'exec title-action'},
            {'key': 'Group2+Super+X', 'description': 'exec grouped-action'},
        ])

    def test_focused_leaf_and_its_output_win_over_focused_ancestors(self):
        tree = focused_tree(app_id='org.xfce.Thunar', output='DP-3')
        tree['nodes'][0]['nodes'][0]['focused'] = True
        snapshot = FixtureProvider(self.replies(tree=tree)).snapshot()

        self.assertEqual(snapshot['app'], 'Thunar')
        self.assertEqual(snapshot['output'], 'DP-3')
        self.assertEqual(snapshot['sections'][0]['coverage'], 'Partial documented baseline')

    def test_unknown_application_is_explicit_and_keeps_sway_second(self):
        snapshot = FixtureProvider(
            self.replies('bindsym Mod4+q kill', tree=focused_tree('org.example.SecretApp')),
        ).snapshot()

        self.assertEqual(snapshot['app'], 'org.example.SecretApp')
        self.assertEqual(snapshot['sections'][0], {
            'title': 'org.example.SecretApp shortcuts',
            'coverage': 'Unavailable: no shortcut profile',
            'rows': [],
        })
        self.assertEqual(snapshot['sections'][1]['title'], 'Sway — default')

    def test_terminal_uses_active_tmux_pane_and_orders_context_sections(self):
        processes = {
            100: {'pid': 100, 'ppid': 1, 'comm': 'foot', 'tty': 0, 'pgrp': 100, 'tpgid': -1},
            110: {'pid': 110, 'ppid': 100, 'comm': 'tmux: client',
                  'tty': 34818, 'pgrp': 110, 'tpgid': 110},
        }
        commands = {
            ('tmux', 'list-clients', '-F', ShortcutProvider.TMUX_CLIENT_FORMAT):
                '110\t$0\t@1\n',
            ('tmux', 'list-panes', '-a', '-F', ShortcutProvider.TMUX_PANE_FORMAT): (
                '$0\t@1\t%1\t0\tnvim\t0\t\n'
                '$0\t@1\t%2\t1\tbtop\t0\t\n'
                '$0\t@2\t%3\t1\tmpv\t0\t\n'
            ),
            ('tmux', 'show-options', '-v', '-t', '$0', 'prefix'): 'C-a\n',
            ('tmux', 'list-keys', '-T', 'prefix'):
                'bind-key -T prefix c new-window\n'
                'bind-key -T prefix % split-window -h\n',
        }
        snapshot = FixtureProvider(
            self.replies(tree=focused_tree('foot', pid=100)),
            commands=commands,
            processes=processes,
        ).snapshot()

        self.assertEqual(snapshot['app'], 'btop')
        self.assertEqual([section['title'] for section in snapshot['sections']], [
            'btop shortcuts', 'Sway — default', 'Foot terminal', 'tmux (Ctrl+A)',
            'System controls',
        ])
        self.assertEqual(snapshot['sections'][3]['rows'], [
            {'key': 'Ctrl+A, c', 'description': 'New window'},
            {'key': 'Ctrl+A, %', 'description': 'Split pane horizontally'},
        ])

    def test_tmux_copy_mode_table_is_added_only_when_pane_reports_it(self):
        processes = {
            100: {'pid': 100, 'ppid': 1, 'comm': 'foot', 'tty': 0, 'pgrp': 100, 'tpgid': -1},
            110: {'pid': 110, 'ppid': 100, 'comm': 'tmux: client',
                  'tty': 34818, 'pgrp': 110, 'tpgid': 110},
        }
        commands = {
            ('tmux', 'list-clients', '-F', ShortcutProvider.TMUX_CLIENT_FORMAT):
                '110\t$0\t@1\n',
            ('tmux', 'list-panes', '-a', '-F', ShortcutProvider.TMUX_PANE_FORMAT):
                '$0\t@1\t%2\t1\tnvim\t1\tcopy-mode\n',
            ('tmux', 'show-options', '-v', '-t', '$0', 'prefix'): 'C-a\n',
            ('tmux', 'show-options', '-wv', '-t', '@1', 'mode-keys'): 'vi\n',
            ('tmux', 'list-keys', '-T', 'prefix'): '',
            ('tmux', 'list-keys', '-T', 'copy-mode-vi'):
                'bind-key -T copy-mode-vi q send-keys -X cancel\n',
        }
        snapshot = FixtureProvider(
            self.replies(tree=focused_tree('foot', pid=100)),
            commands=commands,
            processes=processes,
        ).snapshot()

        tmux = next(section for section in snapshot['sections'] if section['title'].startswith('tmux'))
        self.assertIn({'key': 'q (copy mode)', 'description': 'Exit copy mode'}, tmux['rows'])

    def test_emacs_copy_mode_reads_the_real_copy_mode_table(self):
        processes = {
            100: {'pid': 100, 'ppid': 1, 'comm': 'foot', 'tty': 0,
                  'pgrp': 100, 'tpgid': -1},
            110: {'pid': 110, 'ppid': 100, 'comm': 'tmux: client',
                  'tty': 34818, 'pgrp': 110, 'tpgid': 110},
        }
        commands = {
            ('tmux', 'list-clients', '-F', ShortcutProvider.TMUX_CLIENT_FORMAT):
                '110\t$0\t@1\n',
            ('tmux', 'list-panes', '-a', '-F', ShortcutProvider.TMUX_PANE_FORMAT):
                '$0\t@1\t%2\t1\tnvim\t1\tcopy-mode\n',
            ('tmux', 'show-options', '-v', '-t', '$0', 'prefix'): 'C-b\n',
            ('tmux', 'show-options', '-wv', '-t', '@1', 'mode-keys'): 'emacs\n',
            ('tmux', 'list-keys', '-T', 'prefix'): '',
            ('tmux', 'list-keys', '-T', 'copy-mode'):
                'bind-key -T copy-mode C send-keys -X copy-selection-and-cancel\n',
        }
        snapshot = FixtureProvider(
            self.replies(tree=focused_tree('foot', pid=100)),
            commands=commands, processes=processes).snapshot()

        tmux = next(section for section in snapshot['sections']
                    if section['title'].startswith('tmux'))
        self.assertIn(
            {'key': 'Shift+C (copy mode)',
             'description': 'Copy selection and exit copy mode'}, tmux['rows'])

    def test_tmux_key_case_and_literal_dash_remain_distinct(self):
        rows = ShortcutProvider._tmux_rows(
            'bind-key -T prefix c new-window\n'
            'bind-key -T prefix C previous-window\n'
            'bind-key -T prefix - split-window -h\n',
            'Ctrl+B', copy_mode=False)

        self.assertEqual(rows, [
            {'key': 'Ctrl+B, c', 'description': 'New window'},
            {'key': 'Ctrl+B, Shift+C', 'description': 'Previous window'},
            {'key': 'Ctrl+B, -', 'description': 'Split pane horizontally'},
        ])

    def test_verified_codex_process_uses_partial_versioned_profile(self):
        processes = {
            100: {'pid': 100, 'ppid': 1, 'comm': 'foot', 'tty': 0,
                  'pgrp': 100, 'tpgid': -1},
            110: {'pid': 110, 'ppid': 100, 'comm': 'tmux: client',
                  'tty': 34818, 'pgrp': 110, 'tpgid': 110},
        }
        commands = {
            ('tmux', 'list-clients', '-F', ShortcutProvider.TMUX_CLIENT_FORMAT):
                '110\t$0\t@1\n',
            ('tmux', 'list-panes', '-a', '-F', ShortcutProvider.TMUX_PANE_FORMAT):
                '$0\t@1\t%2\t1\tcodex\t0\t\n',
            ('tmux', 'show-options', '-v', '-t', '$0', 'prefix'): 'C-a\n',
            ('tmux', 'list-keys', '-T', 'prefix'): '',
        }
        snapshot = FixtureProvider(
            self.replies(tree=focused_tree('foot', pid=100)),
            commands=commands,
            processes=processes,
        ).snapshot()

        self.assertEqual(snapshot['app'], 'Codex')
        self.assertEqual(snapshot['sections'][0], {
            'title': 'Codex shortcuts',
            'coverage': 'Partial baseline for Codex CLI 0.153.4',
            'rows': [
                {'key': '?', 'description': 'Show shortcuts (empty composer)'},
                {'key': 'Enter', 'description': 'Submit current draft'},
                {'key': 'Shift+Enter', 'description': 'Insert newline'},
                {'key': 'Tab', 'description': 'Queue message while a task is running'},
                {'key': 'Escape', 'description': 'Interrupt active turn'},
                {'key': 'Ctrl+T', 'description': 'Open transcript'},
                {'key': '/keymap, Enter',
                 'description': 'Browse current Codex keybindings and remappings'},
            ],
        })

    def test_background_tmux_client_does_not_replace_foreground_shell(self):
        processes = {
            100: {'pid': 100, 'ppid': 1, 'comm': 'foot', 'tty': 0, 'pgrp': 100, 'tpgid': -1},
            105: {'pid': 105, 'ppid': 100, 'comm': 'zsh',
                  'tty': 34818, 'pgrp': 105, 'tpgid': 105},
            110: {'pid': 110, 'ppid': 100, 'comm': 'tmux: client',
                  'tty': 34818, 'pgrp': 110, 'tpgid': 105},
        }
        commands = {
            ('tmux', 'list-clients', '-F', ShortcutProvider.TMUX_CLIENT_FORMAT):
                '110\t$0\t@1\n',
            ('tmux', 'list-panes', '-a', '-F', ShortcutProvider.TMUX_PANE_FORMAT):
                '$0\t@1\t%2\t1\tbtop\t0\t\n',
        }
        snapshot = FixtureProvider(
            self.replies(tree=focused_tree('foot', pid=100)),
            commands=commands,
            processes=processes,
        ).snapshot()

        self.assertEqual(snapshot['app'], 'zsh')
        self.assertFalse(any(section['title'].startswith('tmux')
                             for section in snapshot['sections']))

    def test_malformed_custom_profile_is_reported_without_hiding_builtin_profiles(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-shortcuts-test-') as temp:
            path = Path(temp) / 'shortcuts.json'
            path.write_text('{not json', encoding='utf-8')
            snapshot = FixtureProvider(self.replies(), profiles_path=path).snapshot()

        self.assertEqual(snapshot['app'], 'Firefox')
        self.assertTrue(snapshot['sections'][0]['rows'])
        self.assertEqual(snapshot['sections'][-1], {
            'title': 'Local shortcut profiles',
            'coverage': 'Unavailable: invalid JSON',
            'rows': [],
        })

    def test_valid_custom_profile_matches_alias_and_is_strictly_normalized(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-shortcuts-test-') as temp:
            path = Path(temp) / 'shortcuts.json'
            path.write_text(json.dumps({
                'profiles': {
                    'writer': {
                        'name': 'Writer',
                        'aliases': ['org.example.Writer'],
                        'coverage': 'Partial local profile',
                        'rows': [{'key': 'Ctrl+S', 'description': 'Save draft'}],
                    },
                },
            }), encoding='utf-8')
            snapshot = FixtureProvider(
                self.replies(tree=focused_tree('org.example.Writer')),
                profiles_path=path,
            ).snapshot()

        self.assertEqual(snapshot['app'], 'Writer')
        self.assertEqual(snapshot['sections'][0], {
            'title': 'Writer shortcuts',
            'coverage': 'Partial local profile',
            'rows': [{'key': 'Ctrl+S', 'description': 'Save draft'}],
        })

    def test_custom_profile_rejects_text_that_needs_control_character_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-shortcuts-test-') as temp:
            path = Path(temp) / 'shortcuts.json'
            path.write_text(json.dumps({
                'profiles': {
                    'writer': {
                        'name': 'Writer\nUnexpected',
                        'aliases': ['org.example.Writer'],
                        'coverage': 'Partial local profile',
                        'rows': [{'key': 'Ctrl+S', 'description': 'Save draft'}],
                    },
                },
            }), encoding='utf-8')
            snapshot = FixtureProvider(
                self.replies(tree=focused_tree('org.example.Writer')),
                profiles_path=path,
            ).snapshot()

        self.assertEqual(snapshot['app'], 'org.example.Writer')
        self.assertEqual(snapshot['sections'][-1]['coverage'],
                         'Unavailable: invalid schema')

    def test_sway_failure_is_bounded_and_explicit(self):
        replies = self.replies()
        replies[ShortcutProvider.GET_CONFIG] = TimeoutError('slow compositor')
        snapshot = FixtureProvider(replies).snapshot()

        self.assertEqual(snapshot['app'], 'Firefox')
        self.assertEqual(snapshot['sections'][1], {
            'title': 'Sway shortcuts',
            'coverage': 'Unavailable: compositor query failed',
            'rows': [],
        })


if __name__ == '__main__':
    unittest.main()
