import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
INSTALLER = REPO / 'alpine/bin/install-git-mirror-schedule'
loader = importlib.machinery.SourceFileLoader('git_mirror_schedule_test', str(INSTALLER))
spec = importlib.util.spec_from_loader(loader.name, loader)
schedule = importlib.util.module_from_spec(spec)
loader.exec_module(schedule)


class CrontabTests(unittest.TestCase):
    def test_install_preserves_unrelated_jobs_and_line_endings(self):
        existing = '# custom comment  \r\nMAILTO=""\r\n\n17 * * * * wallpaper\n\n\n'
        updated = schedule.update_crontab(existing, 'mirror --scheduled')
        self.assertTrue(updated.startswith(existing))
        self.assertIn('* * * * * mirror --scheduled\n', updated)
        self.assertEqual(schedule.update_crontab(updated, 'mirror --scheduled'), updated)
        self.assertEqual(schedule.update_crontab(updated), existing)

    def test_replacement_retains_block_position_and_other_text(self):
        before, after = '# Before\r\n', '\n0 1 * * * unrelated  \r\n'
        existing = before + schedule.update_crontab('', 'old command') + after
        updated = schedule.update_crontab(existing, 'new command')
        self.assertEqual(updated, before + schedule.update_crontab('', 'new command') + after)
        self.assertEqual(schedule.update_crontab(updated), before + after)

    def test_remove_without_a_block_preserves_bytes_including_missing_newline(self):
        for existing in ('', '# comment', '\n\n', '0 1 * * * untouched\r\n'):
            with self.subTest(existing=existing):
                self.assertEqual(schedule.update_crontab(existing), existing)

    def test_install_separates_unterminated_existing_job(self):
        updated = schedule.update_crontab('0 1 * * * unrelated', 'mirror')
        self.assertTrue(updated.startswith('0 1 * * * unrelated\n' + schedule.BEGIN + '\n'))
        self.assertEqual(schedule.update_crontab(updated, 'mirror'), updated)

    def test_multiple_managed_blocks_collapse_to_one(self):
        block = schedule.update_crontab('', 'mirror')
        updated = schedule.update_crontab(block + '# kept\n' + block, 'replacement')
        self.assertEqual(updated.count(schedule.BEGIN), 1)
        self.assertEqual(schedule.update_crontab(updated), '# kept\n')

    def test_malformed_markers_stop_before_rewriting(self):
        for existing, message in ((schedule.END, 'Orphan'), (schedule.BEGIN, 'Unclosed'),
                                  (schedule.BEGIN + '\n' + schedule.BEGIN, 'Nested')):
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    schedule.update_crontab(existing, 'mirror')

    def test_paths_with_spaces_percent_and_quotes_execute_with_expected_environment(self):
        with tempfile.TemporaryDirectory(prefix='mirror-cron-test-') as temporary:
            root = Path(temporary)
            home = root / "Jack's home 75%"
            repo = root / "dotfiles 'quoted' 100%"
            script = repo / 'alpine/bin/publish-git-mirror'
            script.parent.mkdir(parents=True)
            script.write_text('import json, os, sys\n'
                              'print(json.dumps([sys.argv, os.environ["HOME"], os.environ["PATH"]]))\n')
            command = schedule.cron_command(home, repo)
            self.assertEqual(command.count('\\%'), command.count('%'))
            # A crontab parser removes the quoting backslash before each percent.
            shell_command = command.replace('\\%', '%')
            result = subprocess.run(['/bin/sh', '-c', shell_command], capture_output=True,
                                    text=True, check=True)
            argv, actual_home, actual_path = json.loads(result.stdout)
            self.assertEqual(argv, [str(script), '--scheduled'])
            self.assertEqual(actual_home, str(home))
            self.assertEqual(actual_path, str(home / '.local/bin') + ':/usr/local/bin:/usr/bin:/bin')
            self.assertEqual(shlex.split(shell_command)[3], '/usr/bin/python3')

    def test_newline_and_relative_paths_are_rejected(self):
        for home, repo in (('/home/bad\npath', '/repo'), ('/home/jack', '/bad\rrepo'),
                           ('relative', '/repo'), ('/home/jack', 'relative')):
            with self.subTest(home=home, repo=repo):
                with self.assertRaises(ValueError):
                    schedule.cron_command(home, repo)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mirror-schedule-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        self.crontab = self.root / 'crontab'
        self.writes = self.root / 'writes'
        fake = bin_dir / 'crontab'
        fake.write_text('''#!/usr/bin/python3
import os
from pathlib import Path
import sys
path = Path(os.environ['TEST_CRONTAB'])
if os.environ.get('TEST_CRONTAB_READ_ERROR') and sys.argv[1] == '-l':
    sys.stderr.write('permission denied')
    sys.exit(1)
if sys.argv[1] == '-l':
    if not path.exists():
        sys.stderr.write('no crontab for test user')
        sys.exit(1)
    sys.stdout.buffer.write(path.read_bytes())
elif sys.argv[1] == '-':
    path.write_bytes(sys.stdin.buffer.read())
    with open(os.environ['TEST_CRONTAB_WRITES'], 'a') as stream:
        stream.write('installed\\n')
else:
    sys.exit(2)
''')
        fake.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(bin_dir) + ':/usr/bin:/bin',
                        TEST_CRONTAB=str(self.crontab), TEST_CRONTAB_WRITES=str(self.writes))

    def run_installer(self, *args, check=True):
        return subprocess.run(['/usr/bin/python3', str(INSTALLER), *args], env=self.env,
                              capture_output=True, check=check)

    def test_print_install_idempotence_backup_and_remove_preserve_original_bytes(self):
        original = b'# personal comment \xff\r\n17 * * * * unrelated\n\n\n'
        self.crontab.write_bytes(original)
        proposed = self.run_installer('--print').stdout
        self.assertTrue(proposed.startswith(original))
        self.assertEqual(self.crontab.read_bytes(), original)
        self.assertFalse(self.writes.exists())
        self.assertFalse((self.home / '.local').exists())

        self.run_installer()
        self.assertEqual(self.crontab.read_bytes(), proposed)
        state = self.home / '.local/state/oldbook/git-mirror-schedule'
        backups = list(state.glob('crontab-before-*.txt'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(state.stat().st_mode & 0o777, 0o700)

        self.run_installer()
        self.assertEqual(self.writes.read_text(), 'installed\n')
        self.assertEqual(len(list(state.glob('crontab-before-*.txt'))), 1)
        self.assertEqual(self.run_installer('--remove', '--print').stdout, original)
        self.assertEqual(self.crontab.read_bytes(), proposed)

        self.run_installer('--remove')
        self.assertEqual(self.crontab.read_bytes(), original)
        self.run_installer('--remove')
        self.assertEqual(self.writes.read_text(), 'installed\ninstalled\n')

    def test_no_existing_crontab_installs_normally(self):
        self.run_installer()
        self.assertIn(schedule.BEGIN.encode(), self.crontab.read_bytes())

    def test_read_error_does_not_install_or_create_backup(self):
        self.env['TEST_CRONTAB_READ_ERROR'] = '1'
        result = self.run_installer(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Cannot read existing crontab', result.stderr)
        self.assertFalse(self.writes.exists())
        self.assertFalse((self.home / '.local').exists())


if __name__ == '__main__':
    unittest.main()
