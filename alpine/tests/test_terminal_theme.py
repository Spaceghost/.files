"""Terminal recoloring preserves applications and only writes to owned Foot PTYs."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import pty
import select
import stat
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'alpine/desktop/.local/bin/oldbook-refresh-terminal-theme'


def load_helper():
    loader = importlib.machinery.SourceFileLoader('terminal_theme', str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class TerminalThemeTests(unittest.TestCase):
    def setUp(self):
        self.module = load_helper()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / 'foot.ini'
        self.config.write_text('''[colors-dark]
alpha=0.98
foreground=ebdbb2
background=282828
cursor=282828 fabd2f
selection-background=504945
selection-foreground=fbf1c7
regular0=282828
regular1=cc241d
regular2=98971a
regular3=d79921
regular4=458588
regular5=b16286
regular6=689d6a
regular7=a89984
bright0=928374
bright1=fb4934
bright2=b8bb26
bright3=fabd2f
bright4=83a598
bright5=d3869b
bright6=8ec07c
bright7=ebdbb2
''')
        self.proc = self.root / 'proc'
        self.proc.mkdir()

    def terminal(self, duplicate_fd=False):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        index = int(Path(os.ttyname(slave)).name)
        process = self.proc / '123'
        (process / 'fdinfo').mkdir(parents=True)
        (process / 'fd').mkdir()
        (process / 'exe').symlink_to('/usr/bin/foot')
        fields = ['S'] + ['0'] * 18 + ['1234567'] + ['0'] * 30
        (process / 'stat').write_text('123 (foot) ' + ' '.join(fields))
        for descriptor in ([7, 9] if duplicate_fd else [7]):
            (process / 'fdinfo' / str(descriptor)).write_text(
                f'pos:\t0\nflags:\t02104002\nmnt_id:\t24\nino:\t83\ntty-index:\t{index}\n')
            (process / 'fd' / str(descriptor)).symlink_to('/dev/ptmx')
        return master, slave, index, process

    def test_palette_sets_colors_without_requesting_replies_or_resetting_screen(self):
        packet = self.module.palette_bytes(self.config)
        self.assertIn(b'\x1b]4;0;#282828\x1b\\', packet)
        self.assertIn(b'\x1b]4;15;#ebdbb2\x1b\\', packet)
        self.assertIn(b'\x1b]10;#ebdbb2\x1b\\', packet)
        self.assertIn(b'\x1b]11;[98]#282828\x1b\\', packet)
        self.assertIn(b'\x1b]12;#fabd2f\x1b\\', packet)
        self.assertIn(b'\x1b]17;#504945\x1b\\', packet)
        self.assertIn(b'\x1b]19;#fbf1c7\x1b\\', packet)
        self.assertEqual(packet.count(b'\x1b]'), 21)
        self.assertNotIn(b'?', packet)
        self.assertNotIn(b'\x1bc', packet)
        self.assertNotIn(b'\n', packet)

    def test_invalid_palette_cannot_inject_control_sequences(self):
        original = self.config.read_text()
        for before, after in [('foreground=ebdbb2', 'foreground=ebdbb2\x1b]52;c;anything'),
                              ('alpha=0.98', 'alpha=nan'),
                              ('alpha=0.98', 'alpha=1.01'),
                              ('bright7=ebdbb2', 'bright7='),
                              ('cursor=282828 fabd2f', 'cursor=not-a-color')]:
            with self.subTest(after=after):
                self.config.write_text(original.replace(before, after))
                with self.assertRaises(ValueError):
                    self.module.palette_bytes(self.config)

    def test_duplicate_foot_descriptors_refresh_one_private_pty_once(self):
        master, _, index, _ = self.terminal(duplicate_fd=True)
        packet = self.module.palette_bytes(self.config)
        updated = self.module.refresh_terminals(packet, proc_root=self.proc)
        self.assertEqual(updated, [f'/dev/pts/{index}'])
        self.assertTrue(select.select([master], [], [], 1)[0])
        self.assertEqual(os.read(master, 4096), packet)
        self.assertFalse(select.select([master], [], [], 0)[0])

    def test_other_users_and_non_foot_processes_never_receive_palette(self):
        master, _, _, process = self.terminal()
        with mock.patch.object(self.module.os, 'getuid', return_value=os.getuid() + 1):
            self.assertEqual(self.module.refresh_terminals(b'palette', proc_root=self.proc), [])
        (process / 'exe').unlink()
        (process / 'exe').symlink_to('/usr/bin/python3')
        self.assertEqual(self.module.refresh_terminals(b'palette', proc_root=self.proc), [])
        self.assertFalse(select.select([master], [], [], 0)[0])

    def test_wrong_tty_owner_is_rejected_after_open(self):
        master, _, _, _ = self.terminal()
        real_fstat = os.fstat

        def wrong_owner(descriptor):
            result = real_fstat(descriptor)
            if stat.S_ISCHR(result.st_mode):
                fields = list(result)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return result

        with mock.patch.object(self.module.os, 'fstat', side_effect=wrong_owner):
            self.assertEqual(self.module.refresh_terminals(b'palette', proc_root=self.proc), [])
        self.assertFalse(select.select([master], [], [], 0)[0])

    def test_symlink_and_regular_file_tty_paths_are_left_untouched(self):
        master, slave, index, _ = self.terminal()
        pts = self.root / 'pts'
        pts.mkdir()
        candidate = pts / str(index)
        candidate.symlink_to(os.ttyname(slave))
        self.assertEqual(self.module.refresh_terminals(b'palette', proc_root=self.proc,
                                                     pts_root=pts), [])
        self.assertFalse(select.select([master], [], [], 0)[0])
        candidate.unlink()
        candidate.write_bytes(b'keep this file')
        self.assertEqual(self.module.refresh_terminals(b'palette', proc_root=self.proc,
                                                     pts_root=pts), [])
        self.assertEqual(candidate.read_bytes(), b'keep this file')

    def test_dry_run_reports_targets_without_output_to_their_ptys(self):
        master, _, index, _ = self.terminal()
        self.assertEqual(self.module.refresh_terminals(b'palette', proc_root=self.proc,
                                                     dry_run=True), [f'/dev/pts/{index}'])
        self.assertFalse(select.select([master], [], [], 0)[0])


if __name__ == '__main__':
    unittest.main()
