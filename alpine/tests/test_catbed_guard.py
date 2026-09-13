"""What is held while input is parked: the policy, the holds and the root helper.

The helper is exercised unprivileged against its own sysrq file and ledger; the
real /proc/sys/kernel/sysrq is never touched here, and nothing connects to
elogind or to a compositor.
"""
import contextlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
HELPER = REPO / 'alpine/bin/catbed-sysrq-hold'
INSTALLER = REPO / 'alpine/bin/install-catbed-guard'
HANDLER = REPO / 'alpine/system/acpi/PWRF/00000080'
SHIPPED = REPO / 'alpine/desktop/.config/oldbook/catbed.json'
sys.path.insert(0, str(LIBRARY))
import catbed_guard  # noqa: E402


@contextlib.contextmanager
def environment(**values):
    saved = {name: os.environ.get(name) for name in values}
    os.environ.update({name: value for name, value in values.items() if value is not None})
    for name, value in values.items():
        if value is None:
            os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class PolicyTests(unittest.TestCase):
    def test_the_shipped_default_holds_three_keys_and_narrows_sysrq(self):
        policy = catbed_guard.settings()
        self.assertEqual(policy['keys'], ['power', 'suspend', 'hibernate'])
        self.assertEqual(policy['sysrq'], {'guard': True, 'mask': 382})

    def test_382_is_every_sysrq_function_but_reboot_and_power_off(self):
        self.assertEqual(catbed_guard.DEFAULT_MASK, 2 + 4 + 8 + 16 + 32 + 64 + 256)
        self.assertFalse(catbed_guard.DEFAULT_MASK & 128)

    def test_the_shipped_config_file_is_exactly_the_default(self):
        self.assertEqual(json.loads(SHIPPED.read_text()), catbed_guard.settings())

    def test_a_missing_or_malformed_file_is_the_default(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(catbed_guard.load_settings(Path(directory) / 'none.json'),
                             catbed_guard.settings())
            broken = Path(directory) / 'broken.json'
            broken.write_text('{not json')
            self.assertEqual(catbed_guard.load_settings(broken), catbed_guard.settings())

    def test_one_bad_value_falls_back_alone(self):
        policy = catbed_guard.settings({'keys': ['power', 'lid'],
                                        'sysrq': {'guard': 'yes', 'mask': 0}})
        self.assertEqual(policy['keys'], ['power', 'lid'])
        self.assertTrue(policy['sysrq']['guard'], 'a guard that is not a boolean is the default')
        self.assertEqual(policy['sysrq']['mask'], 0)
        self.assertEqual(catbed_guard.settings({'keys': ['power', 'eject']})['keys'],
                         ['power', 'suspend', 'hibernate'], 'an unknown key discards the list')
        self.assertEqual(catbed_guard.settings({'sysrq': {'mask': 512}})['sysrq']['mask'], 382)
        self.assertEqual(catbed_guard.settings({'sysrq': {'mask': True}})['sysrq']['mask'], 382)

    def test_an_empty_key_list_is_a_choice_and_holds_nothing(self):
        policy = catbed_guard.settings({'keys': []})
        self.assertEqual(policy['keys'], [])
        self.assertEqual(catbed_guard.hold_keys('test', 'why', policy), (None, None))

    def test_the_guard_switched_off_is_a_choice_too(self):
        policy = catbed_guard.settings({'sysrq': {'guard': False}})
        self.assertEqual(catbed_guard.hold_sysrq(policy), (None, None))

    def test_the_inhibitor_is_asked_for_every_key_in_the_login_managers_words(self):
        arguments = catbed_guard.inhibit_arguments(['power', 'suspend', 'hibernate', 'lid'],
                                                   'who', 'why')
        self.assertEqual(arguments[0], '--what=handle-power-key:handle-suspend-key:'
                                       'handle-hibernate-key:handle-lid-switch')
        self.assertIn('--mode=block', arguments)
        self.assertIn('--who=who', arguments)
        self.assertEqual(arguments[-2:], ['--', 'cat'])


class HelperTests(unittest.TestCase):
    """The root helper, run unprivileged against a file that is not the kernel."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='catbed-sysrq-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sysrq = self.root / 'sysrq'
        self.sysrq.write_text('1\n')
        self.state = self.root / 'state'
        self.processes = []
        self.addCleanup(self.reap)

    def reap(self):
        for process, descriptor in self.processes:
            with contextlib.suppress(OSError):
                os.close(descriptor)
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        # Each holder forked a restorer into its own session, and that shadow
        # outlives the holder it releases for: it is still writing the value
        # back and tidying the ledger after the holder is reaped. Removing the
        # temporary directory under it is the race this waits out.
        wait_for(lambda: not self.restorers_alive())

    def restorers_alive(self):
        """Every process still running the helper against this test's state."""
        marker = str(self.state).encode()
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                arguments = (entry / 'cmdline').read_bytes()
            except OSError:
                continue
            if HELPER.name.encode() in arguments and marker in arguments:
                return True
        return False

    def command(self, *arguments):
        return [sys.executable, '-I', str(HELPER), *arguments,
                '--path', str(self.sysrq), '--state', str(self.state)]

    def run_helper(self, *arguments):
        # This machine is slow and this session spawns many subprocesses; a
        # generous timeout keeps the helper's own logic, not scheduling luck,
        # what the test measures.
        return subprocess.run(self.command(*arguments), capture_output=True, text=True, timeout=60)

    def start_hold(self, mask):
        read_fd, write_fd = os.pipe()
        process = subprocess.Popen(self.command('hold', '--mask', str(mask)), stdin=read_fd,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        os.close(read_fd)
        self.processes.append((process, write_fd))
        # Wait for the ledger to actually record this holder rather than for a
        # fixed moment: on a loaded machine the fork, the flock and the write
        # take longer than a poll, and a test that read the ledger too soon
        # would be measuring the load, not the helper.
        line = process.stdout.readline().strip()
        if line == 'holding':
            wait_for(lambda: any(int(h['pid']) == process.pid
                                 for h in json.loads(self.run_helper('status').stdout)['holders']))
        return process, write_fd, line

    def value(self):
        """The synthetic sysrq file's value, or None while the helper is
        mid-write: write_text truncates before it writes, so a reader can
        land on an empty file between the two, and that is not a value."""
        text = self.sysrq.read_text().strip()
        return int(text) if text else None

    def test_the_mask_is_held_while_the_pipe_is_open_and_put_back_when_it_closes(self):
        process, write_fd, line = self.start_hold(382)
        self.assertEqual(line, 'holding')
        self.assertEqual(self.value(), 382)
        os.close(write_fd)
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(self.value(), 1)
        self.assertIn('released: sysrq back to 1', process.stdout.read())

    def test_a_holder_killed_outright_is_released_by_its_restorer(self):
        process, _write_fd, _line = self.start_hold(0)
        self.assertEqual(self.value(), 0)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        self.assertTrue(wait_for(lambda: self.value() == 1), 'the restorer did not put the value back')

    def test_nested_holds_keep_every_holders_restriction_until_the_last_leaves(self):
        first, first_fd, _ = self.start_hold(382)
        second, second_fd, _ = self.start_hold(0)
        self.assertEqual(self.value(), 0)
        os.close(second_fd)
        second.wait(timeout=5)
        self.assertEqual(self.value(), 382, 'the first holder is still owed its mask')
        os.close(first_fd)
        first.wait(timeout=5)
        self.assertEqual(self.value(), 1)

    def test_a_later_looser_hold_never_loosens_an_earlier_one(self):
        _first, _first_fd, _ = self.start_hold(0)
        _second, _second_fd, line = self.start_hold(382)
        self.assertEqual(line, 'holding')
        self.assertEqual(self.value(), 0)

    def test_a_ledger_left_by_a_crash_remembers_the_real_baseline(self):
        # A crash that took the restorer with it: the file says 382, the
        # ledger says the kernel had 1 before anyone touched it.
        (self.state / 'holders').mkdir(parents=True)
        (self.state / 'baseline').write_text('1\n')
        self.sysrq.write_text('382\n')
        process, write_fd, line = self.start_hold(0)
        self.assertEqual(line, 'holding')
        os.close(write_fd)
        process.wait(timeout=5)
        self.assertEqual(self.value(), 1, 'the narrowed value was mistaken for the baseline')

    def test_restore_refuses_while_a_holder_is_alive_and_tidies_after_one_is_gone(self):
        process, _write_fd, _ = self.start_hold(0)
        result = self.run_helper('restore')
        self.assertEqual(result.returncode, 1)
        self.assertIn('holding', result.stdout)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        self.assertTrue(wait_for(lambda: self.value() == 1))
        result = self.run_helper('restore')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('nothing to do', result.stdout)

    def test_status_reports_the_value_the_baseline_and_the_holders(self):
        process, _write_fd, _ = self.start_hold(382)
        document = json.loads(self.run_helper('status').stdout)
        self.assertEqual(document['sysrq'], 382)
        self.assertEqual(document['baseline'], 1)
        self.assertEqual([holder['pid'] for holder in document['holders']], [process.pid])

    def test_an_unwritable_file_is_a_refusal_that_leaves_nothing_behind(self):
        self.sysrq.chmod(0o444)
        if os.geteuid() == 0:
            self.skipTest('root can write anything')
        process, _write_fd, line = self.start_hold(0)
        self.assertEqual(process.wait(timeout=5), 1)
        self.assertIn('cannot write', line)
        self.assertEqual(json.loads(self.run_helper('status').stdout)['holders'], [])

    def test_the_mask_is_bounded_and_the_real_kernel_needs_root(self):
        self.assertEqual(self.run_helper('hold', '--mask', '512').returncode, 2)
        if os.geteuid() != 0:
            result = subprocess.run([sys.executable, '-I', str(HELPER), 'status'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('root', result.stderr)

    def test_the_helper_runs_isolated_and_imports_nothing_from_home(self):
        text = HELPER.read_text()
        self.assertEqual(text.splitlines()[0], '#!/usr/bin/python3 -I')
        self.assertNotIn('sys.path', text)
        self.assertTrue(HELPER.stat().st_mode & 0o111)


class HoldTests(unittest.TestCase):
    """The client side: the descriptor is the hold, and a refusal is named."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='catbed-hold-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sysrq = self.root / 'sysrq'
        self.sysrq.write_text('1\n')

    def policy(self, mask=0, keys=()):
        return catbed_guard.settings({'keys': list(keys), 'sysrq': {'guard': True, 'mask': mask}})

    def test_the_sysrq_hold_is_taken_through_the_helper_and_released_with_the_descriptor(self):
        with environment(CATBED_SYSRQ_HELPER=str(HELPER), CATBED_SYSRQ_PATH=str(self.sysrq),
                         CATBED_SYSRQ_STATE=str(self.root / 'state')):
            descriptor, problem = catbed_guard.hold_sysrq(self.policy(mask=0))
        self.assertIsNone(problem)
        self.assertIsNotNone(descriptor)
        self.assertEqual(int(self.sysrq.read_text()), 0)
        os.close(descriptor)
        self.assertTrue(wait_for(lambda: int(self.sysrq.read_text()) == 1))

    def test_a_helper_that_refuses_is_a_named_problem_and_no_hold(self):
        # Override helpers run under sys.executable, so the fake is Python.
        refusing = self.root / 'refusing'
        refusing.write_text('import sys\nprint("released: the kernel said no", file=sys.stderr)\n'
                            'sys.exit(1)\n')
        with environment(CATBED_SYSRQ_HELPER=str(refusing)):
            descriptor, problem = catbed_guard.hold_sysrq(self.policy())
        self.assertIsNone(descriptor)
        self.assertIn('the kernel said no', problem)
        self.assertTrue(problem.loud)

    def test_a_helper_that_never_says_holding_is_not_believed(self):
        silent = self.root / 'silent'
        silent.write_text('import sys\nsys.stdin.read()\n')
        with environment(CATBED_SYSRQ_HELPER=str(silent)):
            descriptor, problem = catbed_guard.hold_sysrq(self.policy())
        # Deliberately short: the module waits CONFIRM_SECONDS for the word.
        self.assertIsNone(descriptor)
        self.assertIn('never said', problem)

    def test_an_uninstalled_helper_is_a_quiet_problem(self):
        with environment(CATBED_SYSRQ_HELPER=None):
            missing = Path(catbed_guard.SYSRQ_HELPER)
            if missing.exists():
                self.skipTest('the helper is installed on this machine')
            descriptor, problem = catbed_guard.hold_sysrq(self.policy())
        self.assertIsNone(descriptor)
        self.assertFalse(problem.loud)
        self.assertIn('install-catbed-guard', problem)

    def test_the_keys_are_held_by_whichever_inhibitor_the_host_has(self):
        fake_bin = self.root / 'bin'
        fake_bin.mkdir()
        for inhibitor in ('elogind-inhibit', 'systemd-inhibit'):
            with self.subTest(inhibitor=inhibitor):
                for stale in fake_bin.iterdir():
                    stale.unlink()
                record = self.root / f'{inhibitor}.args'
                script = fake_bin / inhibitor
                script.write_text('#!/bin/sh\n'
                                  f'printf "%s\\n" "$@" > {record}\n'
                                  'while [ "$1" != "--" ]; do shift; done\n'
                                  'shift\n'
                                  f'echo $$ > {self.root / "pid"}\n'
                                  'exec "$@"\n')
                script.chmod(0o755)
                (fake_bin / 'cat').symlink_to(shutil.which('cat'))
                with environment(PATH=str(fake_bin)):
                    descriptor, problem = catbed_guard.hold_keys(
                        'test', 'because', self.policy(keys=('power', 'suspend', 'hibernate')))
                self.assertIsNone(problem)
                self.assertTrue(wait_for(record.exists))
                arguments = record.read_text().split()
                self.assertEqual(arguments[0],
                                 '--what=handle-power-key:handle-suspend-key:handle-hibernate-key')
                self.assertIn('--mode=block', arguments)
                pid = int((self.root / 'pid').read_text())
                os.kill(pid, 0)
                os.close(descriptor)

                def gone():
                    # The holder is our own child, so it lingers as a zombie
                    # until reaped: exited counts, not only vanished.
                    try:
                        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                    except OSError:
                        return True
                    return fields[0] in ('Z', 'X')
                self.assertTrue(wait_for(gone), 'closing the descriptor did not release the hold')

    def test_hold_all_takes_what_it_can_and_names_what_it_could_not(self):
        refusing = self.root / 'refusing'
        refusing.write_text('import sys\nprint("released: no", file=sys.stderr)\nsys.exit(1)\n')
        with environment(PATH=str(self.root / 'nowhere'), CATBED_SYSRQ_HELPER=str(refusing)):
            descriptors, problems = catbed_guard.hold_all('test', 'why', self.policy(keys=('power',)))
        self.assertEqual(descriptors, [])
        self.assertEqual(len(problems), 2)
        self.assertTrue(all(isinstance(problem, str) for problem in problems))

    def test_announce_speaks_only_for_loud_problems(self):
        calls = []
        original = catbed_guard.subprocess.Popen
        catbed_guard.subprocess.Popen = lambda *a, **k: calls.append(a[0])
        try:
            catbed_guard.announce('x', [catbed_guard.Quiet('nothing installed')])
            self.assertEqual(calls, [])
            catbed_guard.announce('x', [catbed_guard.Quiet('nothing'), catbed_guard.Problem('bad')])
            self.assertEqual(len(calls), 1)
            self.assertIn('critical', calls[0])
        finally:
            catbed_guard.subprocess.Popen = original


class InstallerTests(unittest.TestCase):
    def test_check_reports_every_managed_file_without_root(self):
        result = subprocess.run([sys.executable, str(INSTALLER), '--check'],
                                capture_output=True, text=True, timeout=10)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertIn('/usr/local/sbin/catbed-sysrq-hold', result.stdout)
        self.assertIn('/etc/acpi/PWRF/00000080', result.stdout)

    def test_the_acpid_handler_does_nothing_at_all(self):
        lines = [line.strip() for line in HANDLER.read_text().splitlines()]
        self.assertEqual(lines[0], '#!/bin/sh')
        commands = [line for line in lines[1:] if line and not line.startswith('#')]
        self.assertEqual(commands, ['exit 0'])
        self.assertEqual(subprocess.run(['sh', str(HANDLER)], timeout=5).returncode, 0)


if __name__ == '__main__':
    unittest.main()
