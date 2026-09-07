# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared-process terminal windows must not impersonate the focused tab."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hold_to_help.sources import ShortcutProvider


class PortableTerminalTests(unittest.TestCase):
    def setUp(self):
        self.provider = ShortcutProvider('unused')
        self.processes = {
            100: {'pid': 100, 'ppid': 1, 'tty': 0, 'pgrp': 100, 'tpgid': -1,
                  'comm': 'qterminal'},
            101: {'pid': 101, 'ppid': 100, 'tty': 1, 'pgrp': 101, 'tpgid': 101,
                  'comm': 'nvim'},
            102: {'pid': 102, 'ppid': 100, 'tty': 2, 'pgrp': 102, 'tpgid': 102,
                  'comm': 'btop'},
        }

    def test_multiple_foreground_terminal_ttys_keep_terminal_context(self):
        with patch.object(self.provider, '_process_snapshot', return_value=self.processes), \
                patch.object(self.provider, '_run_command', return_value=''):
            identity, tmux = self.provider._terminal_identity({'pid': 100}, 'qterminal')
        self.assertEqual(identity, 'qterminal')
        self.assertIsNone(tmux)

    def test_multiple_tmux_clients_do_not_guess_visible_window(self):
        self.processes[101]['comm'] = self.processes[102]['comm'] = 'tmux'
        def command(argv):
            if argv[1] == 'list-clients':
                return '101\t$1\t@1\n102\t$2\t@2\n'
            return '$1\t@1\t%1\t1\tnvim\t0\t\n$2\t@2\t%2\t1\tbtop\t0\t\n'
        with patch.object(self.provider, '_process_snapshot', return_value=self.processes), \
                patch.object(self.provider, '_run_command', side_effect=command):
            self.assertEqual(self.provider._terminal_identity({'pid': 100}, 'konsole'),
                             ('konsole', None))

    def test_single_foreground_tty_preserves_application_detection(self):
        del self.processes[102]
        with patch.object(self.provider, '_process_snapshot', return_value=self.processes), \
                patch.object(self.provider, '_run_command', return_value=''):
            self.assertEqual(self.provider._terminal_identity({'pid': 100}, 'qterminal'),
                             ('nvim', None))


if __name__ == '__main__':
    unittest.main()
