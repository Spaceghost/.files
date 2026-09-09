"""The fans come back. From every exit the helper has, including the ones it cannot catch.

This is the test file that matters most in the whole feature. `fan1_manual=1`
is a latch the kernel never clears, so a helper that dies holding it leaves a
laptop with no automatic cooling. Every path out of that state is exercised
here against a synthetic sysfs tree, including `kill -9`, which the helper
cannot catch and which is therefore covered by the restorer it forks.

Nothing here touches the real Apple SMC.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/bin/oldbook-fan-hold'
LIBRARY = REPO / 'alpine/desktop/.local/lib/oldbook'
sys.path.insert(0, str(LIBRARY))
import thermal  # noqa: E402


def load_helper():
    loader = importlib.machinery.SourceFileLoader('oldbook_fan_hold', str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


helper = load_helper()


def wait_until(predicate, timeout=20.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class Machine:
    """A synthetic applesmc directory and coretemp hwmon, writable by the test."""

    def __init__(self, base, fans=(1, 2), celsius=45.0):
        self.smc = Path(base) / 'applesmc.768'
        self.hwmon = Path(base) / 'hwmon'
        self.smc.mkdir(parents=True)
        (self.hwmon / 'hwmon0').mkdir(parents=True)
        (self.hwmon / 'hwmon0/name').write_text('coretemp\n')
        self.celsius(celsius)
        for index in fans:
            (self.smc / f'fan{index}_manual').write_text('0\n')
            (self.smc / f'fan{index}_output').write_text('5000\n')
            (self.smc / f'fan{index}_min').write_text('2000\n')
            (self.smc / f'fan{index}_input').write_text('4800\n')

    def celsius(self, value):
        (self.hwmon / 'hwmon0/temp1_input').write_text(f'{int(value * 1000)}\n')

    def field(self, index, name):
        try:
            return (self.smc / f'fan{index}_{name}').read_text().strip()
        except OSError:
            return None

    def automatic(self, *indexes):
        return all(self.field(index, 'manual') == '0' for index in indexes or (1, 2))

    def manual(self, *indexes):
        return all(self.field(index, 'manual') == '1' for index in indexes or (1, 2))


class HoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.machine = Machine(self.tmp.name)
        self.log = Path(self.tmp.name) / 'helper.log'
        self.process = None
        self.sink = None
        self.addCleanup(self.reap)

    def reap(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            if self.process.stdin is not None and not self.process.stdin.closed:
                self.process.stdin.close()
            # The restorer writes after the holder is gone, which is the entire
            # point of it. Wait for that write before the fixture is torn down,
            # or it lands in a directory that is being deleted.
            wait_until(self.machine.automatic, timeout=15)
            time.sleep(0.2)
        if self.sink is not None:
            self.sink.close()

    def hold(self, regime='open', deadline=60.0):
        self.log.write_text('')
        self.sink = self.log.open('w')
        self.process = subprocess.Popen(
            [sys.executable, str(HELPER), 'hold', '--root', str(self.machine.smc),
             '--hwmon', str(self.machine.hwmon), '--regime', regime,
             '--deadline', str(deadline)],
            stdin=subprocess.PIPE, stdout=self.sink, stderr=subprocess.STDOUT,
            start_new_session=True)
        self.assertTrue(wait_until(lambda: 'holding' in self.log.read_text()),
                        'the helper never reported taking the hold')
        self.assertTrue(self.machine.manual(), 'the fans were not switched to manual')
        return self.process

    def assert_released(self, note=None):
        self.assertTrue(wait_until(self.machine.automatic),
                        f'the fans were left on manual: {self.log.read_text()!r}')
        self.assertEqual(self.machine.field(1, 'output'), '5000')
        self.assertEqual(self.machine.field(1, 'min'), '2000')
        if note is not None:
            self.assertTrue(wait_until(lambda: note in self.log.read_text()),
                            f'expected {note!r} in {self.log.read_text()!r}')

    # ---- the ordinary ways out ---------------------------------------------

    def test_the_hold_is_taken_at_each_fan_own_minimum(self):
        self.hold()
        self.assertEqual(self.machine.field(1, 'output'), '2000')
        self.assertEqual(self.machine.field(2, 'output'), '2000')

    def test_release_gives_the_fans_back(self):
        process = self.hold()
        process.stdin.write(b'release\n')
        process.stdin.flush()
        self.assert_released('the caller asked')
        self.assertEqual(process.wait(timeout=10), 0)

    def test_closing_the_pipe_gives_the_fans_back(self):
        """The caller dying is the ordinary case, and a closed pipe is what that looks like."""
        process = self.hold()
        process.stdin.close()
        self.assert_released()
        self.assertEqual(process.wait(timeout=10), 0)

    def test_sigterm_gives_the_fans_back(self):
        process = self.hold()
        process.send_signal(signal.SIGTERM)
        self.assert_released()
        process.wait(timeout=10)

    def test_sighup_gives_the_fans_back(self):
        process = self.hold()
        process.send_signal(signal.SIGHUP)
        self.assert_released()
        process.wait(timeout=10)

    # ---- the ones the helper cannot catch ----------------------------------

    def test_kill_dash_nine_gives_the_fans_back(self):
        """The whole reason the restorer exists: this signal cannot be handled."""
        process = self.hold()
        process.kill()
        process.wait(timeout=10)
        self.assertTrue(wait_until(self.machine.automatic),
                        'a killed holder left the fans on manual')

    def test_killing_the_whole_process_group_still_gives_the_fans_back(self):
        """The restorer runs in its own session, so a group kill cannot reach it."""
        process = self.hold()
        group = os.getpgid(process.pid)
        # Never signal our own group: the helper is started in its own session
        # precisely so this test can kill a group without killing the runner.
        self.assertNotEqual(group, os.getpgid(0))
        os.killpg(group, signal.SIGKILL)
        process.wait(timeout=10)
        self.assertTrue(wait_until(self.machine.automatic),
                        'a killed process group left the fans on manual')

    def test_a_caller_that_stops_renewing_loses_the_hold(self):
        """A wedged caller is as dangerous as a dead one, so the hold expires."""
        process = self.hold(deadline=1.5)
        self.assert_released('stopped renewing')
        process.wait(timeout=10)

    def test_renewing_keeps_the_hold_alive_past_the_deadline(self):
        process = self.hold(deadline=1.5)
        for _ in range(6):
            process.stdin.write(b'renew open\n')
            process.stdin.flush()
            time.sleep(0.5)
        self.assertTrue(self.machine.manual(), 'a renewed hold was dropped anyway')
        process.stdin.close()
        self.assert_released()

    # ---- its own eyes ------------------------------------------------------

    def test_a_core_past_the_release_line_ends_the_hold_without_being_told(self):
        process = self.hold(regime='open')
        self.machine.celsius(thermal.REGIMES['open']['fan_release'] + 1)
        self.assert_released('release line')
        process.wait(timeout=10)

    def test_the_closed_lid_release_line_is_the_stricter_one(self):
        process = self.hold(regime='closed')
        self.machine.celsius(thermal.REGIMES['closed']['fan_release'] + 1)
        self.assert_released('release line')
        process.wait(timeout=10)
        self.assertLess(thermal.REGIMES['closed']['fan_release'],
                        thermal.REGIMES['open']['fan_release'])

    def test_an_unreadable_core_temperature_ends_the_hold(self):
        process = self.hold()
        (self.machine.hwmon / 'hwmon0/temp1_input').unlink()
        self.assert_released('no readable core temperature')
        process.wait(timeout=10)

    def test_a_nonsense_core_temperature_ends_the_hold(self):
        process = self.hold()
        (self.machine.hwmon / 'hwmon0/temp1_input').write_text('not a number\n')
        self.assert_released('no readable core temperature')
        process.wait(timeout=10)


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.machine = Machine(self.tmp.name)

    def run_helper(self, *arguments):
        return subprocess.run([sys.executable, str(HELPER), *arguments],
                              capture_output=True, text=True, timeout=30)

    def test_a_symlinked_fan_control_is_refused_before_anything_is_written(self):
        target = Path(self.tmp.name) / 'elsewhere'
        target.write_text('0\n')
        (self.machine.smc / 'fan1_manual').unlink()
        (self.machine.smc / 'fan1_manual').symlink_to(target)
        done = self.run_helper('hold', '--root', str(self.machine.smc),
                               '--hwmon', str(self.machine.hwmon), '--deadline', '5')
        self.assertEqual(done.returncode, 1)
        self.assertIn('symlink', done.stdout + done.stderr)
        self.assertEqual(target.read_text().strip(), '0')

    def test_a_machine_with_no_fans_holds_nothing_and_says_so(self):
        empty = Path(self.tmp.name) / 'nofans'
        empty.mkdir()
        done = self.run_helper('hold', '--root', str(empty),
                               '--hwmon', str(self.machine.hwmon), '--deadline', '5')
        self.assertEqual(done.returncode, 1)
        self.assertIn('no controllable fans', done.stdout)

    def test_a_root_that_is_not_a_directory_is_refused(self):
        done = self.run_helper('hold', '--root', str(self.machine.smc / 'fan1_manual'))
        self.assertEqual(done.returncode, 1)

    def test_a_zero_deadline_is_refused_rather_than_meaning_forever(self):
        done = self.run_helper('hold', '--root', str(self.machine.smc), '--deadline', '0')
        self.assertEqual(done.returncode, 1)

    def test_restore_puts_a_stranded_manual_fan_back(self):
        """The recovery lever, for the one failure the pipe cannot cover."""
        (self.machine.smc / 'fan1_manual').write_text('1\n')
        done = self.run_helper('restore', '--root', str(self.machine.smc))
        self.assertEqual(done.returncode, 0)
        self.assertEqual(self.machine.field(1, 'manual'), '0')
        self.assertIn('fan1', done.stdout)

    def test_restore_on_a_healthy_machine_writes_nothing(self):
        done = self.run_helper('restore', '--root', str(self.machine.smc))
        self.assertEqual(done.returncode, 0)
        self.assertIn('nothing to do', done.stdout)

    def test_the_fan_path_guard_only_ever_names_a_fan_control(self):
        for field in ('manual', 'output', 'min'):
            self.assertTrue(str(helper.fan_path(self.machine.smc, 1, field))
                            .endswith(f'fan1_{field}'))
        with self.assertRaises(ValueError):
            helper.fan_path(self.machine.smc, 1, '../../../etc/passwd')
        with self.assertRaises(ValueError):
            helper.fan_path(self.machine.smc, 1, 'input')


class ContractTests(unittest.TestCase):
    """The helper carries a copy of two numbers; the copy must not drift."""

    def test_the_release_lines_still_match_the_thermal_table(self):
        for name, limits in thermal.REGIMES.items():
            self.assertIn(name, helper.FAN_RELEASE)
            self.assertEqual(helper.FAN_RELEASE[name], limits['fan_release'],
                             f'{name}: the helper and thermal.py disagree about fan_release')
        self.assertEqual(sorted(helper.FAN_RELEASE), sorted(thermal.REGIMES))

    def test_the_helper_imports_nothing_from_the_user_home(self):
        """A root process must not execute code out of a directory the user can write."""
        source = HELPER.read_text()
        self.assertNotIn('sys.path.insert', source)
        self.assertNotIn('lib/oldbook', source)

    def test_a_helper_pointed_at_the_real_smc_needs_root(self):
        self.assertFalse(helper.privileged_enough(Path(helper.DEFAULT_ROOT),
                                                  helper.DEFAULT_ROOT)
                         and os.geteuid() != 0)
        self.assertTrue(helper.privileged_enough(Path('/tmp/synthetic'), helper.DEFAULT_ROOT))

    def test_the_deadline_clock_survives_a_suspend(self):
        """CLOCK_BOOTTIME, so a machine that sleeps for hours wakes on automatic."""
        self.assertIn('CLOCK_BOOTTIME', HELPER.read_text())


class ClientTests(unittest.TestCase):
    """What the desktop side will and will not run as root."""

    def setUp(self):
        import cat_bed
        self.cat_bed = cat_bed
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = {name: os.environ.get(name) for name in ('OLDBOOK_FAN_HELPER',)}
        self.addCleanup(self.restore_environment)
        os.environ.pop('OLDBOOK_FAN_HELPER', None)

    def restore_environment(self):
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_a_helper_the_user_could_rewrite_is_never_run_as_root(self):
        impostor = Path(self.tmp.name) / 'oldbook-fan-hold'
        impostor.write_text('#!/bin/sh\nexit 0\n')
        impostor.chmod(0o755)
        original = self.cat_bed.HELPER
        try:
            self.cat_bed.HELPER = str(impostor)
            self.assertIsNone(self.cat_bed.helper_command('restore'))
        finally:
            self.cat_bed.HELPER = original

    def test_a_missing_helper_is_reported_rather_than_assumed(self):
        original = self.cat_bed.HELPER
        try:
            self.cat_bed.HELPER = str(Path(self.tmp.name) / 'absent')
            self.assertIsNone(self.cat_bed.helper_command('restore'))
            self.assertIsNone(self.cat_bed.restore_fans())
        finally:
            self.cat_bed.HELPER = original

    def test_the_test_helper_is_run_unprivileged_and_never_through_doas(self):
        os.environ['OLDBOOK_FAN_HELPER'] = str(HELPER)
        command = self.cat_bed.helper_command('hold', regime='open', deadline=5)
        self.assertNotIn('doas', command)
        self.assertIn('--regime', command)
        self.assertIn('open', command)


if __name__ == '__main__':
    unittest.main()
