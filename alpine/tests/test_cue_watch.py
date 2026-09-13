"""oldbook-cue-watch must never use a destructive fossil update, must detect
and loudly refuse a real merge conflict instead of running cue-sync over a
half-merged tree, and must not double-run when a second instance starts
while the lock is already held.

These tests exercise it against throwaway Fossil repositories created under
tempfile.TemporaryDirectory -- never against the real
~/.local/share/fossil/files.fossil or the real ~/.files checkout.
"""
import importlib.machinery
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'alpine/desktop/.local/bin/oldbook-cue-watch'


def load_helper():
    loader = importlib.machinery.SourceFileLoader('oldbook_cue_watch', str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ConflictDetectionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_helper()

    def test_matches_fossil_conflict_count_line(self):
        self.assertTrue(self.module._CONFLICT_RE.search('***** 1 merge conflicts in shared.txt'))

    def test_matches_fossil_warning_line(self):
        self.assertTrue(self.module._CONFLICT_RE.search('WARNING: 1 merge conflicts'))

    def test_clean_update_output_does_not_match(self):
        clean = ('updated-to:   abc123 2026-09-13\n'
                  'tags:         trunk\n'
                  'changes:      1 file modified.\n')
        self.assertFalse(self.module._CONFLICT_RE.search(clean))


@unittest.skipUnless(shutil.which('fossil'), 'fossil is not installed')
class FossilUpdateTests(unittest.TestCase):
    """Real, throwaway Fossil repos -- never the real files.fossil."""

    def setUp(self):
        self.module = load_helper()
        self.temporary = tempfile.TemporaryDirectory(prefix='oldbook-cue-watch-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo_file = self.root / 'test.fossil'
        self.checkout_a = self.root / 'checkout-a'
        self.checkout_b = self.root / 'checkout-b'
        self.fossil('init', str(self.repo_file), cwd=self.root)
        self.checkout_a.mkdir()
        self.checkout_b.mkdir()
        self.fossil('open', str(self.repo_file), cwd=self.checkout_a)
        self.fossil('open', str(self.repo_file), cwd=self.checkout_b)

        # A stub cue-sync that just records that it ran, so tests can assert
        # on "did the apply step happen" without touching a real Waybar.
        bin_dir = self.checkout_a / 'alpine/bin'
        bin_dir.mkdir(parents=True)
        self.cue_sync_marker = self.checkout_a / 'cue-sync-ran'
        stub = bin_dir / 'cue-sync'
        stub.write_text(
            '#!/usr/bin/env python3\n'
            'from pathlib import Path\n'
            f"Path({str(self.cue_sync_marker)!r}).write_text('ran\\n')\n"
        )
        stub.chmod(0o755)

        self.module.REPO_FILE = self.repo_file
        self.module.CHECKOUT = self.checkout_a
        self.module.CUE_SYNC = bin_dir / 'cue-sync'

    def fossil(self, *arguments, cwd):
        subprocess.run(['fossil', *arguments], cwd=str(cwd), check=True,
                        capture_output=True, text=True)

    def commit(self, checkout, path, content, message):
        (checkout / path).write_text(content)
        try:
            self.fossil('add', path, cwd=checkout)
        except subprocess.CalledProcessError:
            pass  # already tracked from an earlier commit in this test
        self.fossil('commit', '-m', message, '--no-warnings', cwd=checkout)

    def test_clean_commit_updates_checkout_and_runs_cue_sync(self):
        self.commit(self.checkout_b, 'new-file.txt', 'hello\n', 'add new-file.txt')
        self.module.handle_commit()
        self.assertTrue((self.checkout_a / 'new-file.txt').exists(),
                         'fossil update in checkout-a should have pulled the commit from checkout-b')
        self.assertTrue(self.cue_sync_marker.exists(), 'cue-sync should have run after a clean update')

    def test_fossil_update_never_passes_force(self):
        from unittest import mock
        with mock.patch.object(self.module.subprocess, 'run',
                                wraps=self.module.subprocess.run) as run:
            self.module.fossil_update(self.checkout_a)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments, ['fossil', 'update'],
                          'fossil_update must run plain `fossil update`, no --force or other flags')

    def test_conflicting_commit_is_detected_and_cue_sync_is_skipped(self):
        self.commit(self.checkout_a, 'shared.txt', 'line one\nline two\nline three\n', 'add shared.txt')
        self.fossil('update', cwd=self.checkout_b)
        (self.checkout_a / 'shared.txt').write_text('line one\nA local edit\nline three\n')
        (self.checkout_b / 'shared.txt').write_text('line one\nB committed edit\nline three\n')
        self.fossil('commit', '-m', 'b edits line two', '--no-warnings', cwd=self.checkout_b)

        self.module.handle_commit()

        self.assertFalse(self.cue_sync_marker.exists(),
                          'cue-sync must not run when fossil update hit a real merge conflict')
        self.assertIn('<<<<<<<', (self.checkout_a / 'shared.txt').read_text(),
                       'the conflict markers fossil left in the file must still be there for a human to resolve')

    def test_cue_sync_failure_is_reported_and_does_not_raise(self):
        self.module.CUE_SYNC.write_text('#!/usr/bin/env python3\nimport sys\nsys.exit("boom")\n')
        self.module.CUE_SYNC.chmod(0o755)
        self.commit(self.checkout_b, 'another-file.txt', 'x\n', 'add another-file.txt')
        # Must not raise -- a failing cue-sync is reported to stderr, not fatal to the watcher.
        self.module.handle_commit()


@unittest.skipUnless(shutil.which('fossil'), 'fossil is not installed')
class SingleInstanceLockTests(unittest.TestCase):
    def setUp(self):
        self.module = load_helper()
        self.temporary = tempfile.TemporaryDirectory(prefix='oldbook-cue-watch-lock-')
        self.addCleanup(self.temporary.cleanup)
        import os
        self._environ_patch = {'XDG_RUNTIME_DIR': self.temporary.name}
        self._old_environ = {key: os.environ.get(key) for key in self._environ_patch}
        os.environ.update(self._environ_patch)
        self.addCleanup(lambda: os.environ.update(
            {k: v for k, v in self._old_environ.items() if v is not None}))

    def test_second_instance_does_not_acquire_the_lock(self):
        first = self.module.acquire_lock()
        self.assertIsNotNone(first)
        second = self.module.acquire_lock()
        self.assertIsNone(second, 'a second instance must not double-acquire the lock')
        first.close()


class SelfTriggeredWriteTests(unittest.TestCase):
    """handle_commit() (fossil update, then cue-sync) writes through the very
    file being watched -- a no-op update still touches its own bookkeeping
    tables. Undrained, that write queues a fresh event indistinguishable from
    a real external commit, so handling one real commit re-triggers itself on
    its own write, forever: a tight loop that pins a core and holds the
    repository's database locked against every other commit.
    """

    class StopWatching(Exception):
        pass

    class ScriptedInotify:
        """One real external event, then one self-triggered event pushed by
        the mocked handle_commit() itself, mimicking fossil update's own
        write landing while handle_commit() was running."""

        def __init__(self):
            self.fd = 99
            self._queued = ['external-commit']
            self.watched = None

        def add_watch(self, path, mask):
            self.watched = path

        def read_events(self):
            if not self._queued:
                # The unguarded call at the top of watch_forever's loop is the
                # real blocking wait for the next external event; with nothing
                # queued, a real Inotify would block here. Raising instead
                # ends the test at exactly the point that matters: the loop
                # correctly returned to waiting rather than calling
                # handle_commit() again for its own write.
                raise SelfTriggeredWriteTests.StopWatching(
                    'reached the blocking wait for a genuinely external event')
            events, self._queued = self._queued, []
            return events

        def push_self_triggered_event(self):
            self._queued.append('self-triggered')

    def test_handle_commits_own_write_does_not_retrigger_it(self):
        module = load_helper()
        inotify = self.ScriptedInotify()
        calls = []

        def fake_handle_commit():
            calls.append(1)
            if len(calls) == 1:
                # Simulate fossil update/cue-sync's own write landing on the
                # watched file while handle_commit() was still running.
                inotify.push_self_triggered_event()
            else:
                raise self.StopWatching('a second call means the self-triggered '
                                        'write was not drained')

        # select.select is asked twice per iteration: once to drain any burst
        # before handle_commit(), once after to drain handle_commit()'s own
        # write. "Ready" exactly when the scripted inotify has something
        # queued -- true right after push_self_triggered_event(), false once
        # read_events() has consumed it.
        def fake_select(rlist, wlist, xlist, timeout):
            return (rlist, [], []) if inotify._queued else ([], [], [])

        with unittest.mock.patch.object(module, 'handle_commit', fake_handle_commit), \
             unittest.mock.patch.object(module.select, 'select', fake_select):
            with self.assertRaises(self.StopWatching):
                module.watch_forever(inotify=inotify, debounce_seconds=0,
                                     min_interval_seconds=0)

        self.assertEqual(calls, [1], 'handle_commit() must not be called again '
                                     'for the write it just made itself')

    def test_min_interval_bounds_the_rate_even_if_the_drain_ever_misses(self):
        """Live evidence: the drain above did not hold up under real
        concurrent load even once implemented -- the same repeat happened
        anyway. min_interval_seconds is the actual guarantee: whatever wakes
        the loop, however often, handle_commit() cannot run twice closer
        together than this, so a self-triggering loop is capped at a steady
        rate instead of spinning as fast as fossil/cue-sync can be spawned.
        """
        module = load_helper()
        calls = []
        # A fake clock advances only when the loop itself sleeps, so the test
        # proves the *requested* sleep duration is correct without a real
        # multi-second wait.
        clock = {'now': 0.0}

        def fake_monotonic():
            return clock['now']

        def fake_sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            clock['now'] += seconds

        def fake_handle_commit():
            calls.append(clock['now'])
            if len(calls) >= 3:
                raise self.StopWatching('enough calls observed')

        class AlwaysReadyInotify:
            """The adversarial case the drain cannot fully rule out: every
            wait, at every point in the loop, finds an event already queued
            -- self-triggered or otherwise. Only min_interval_seconds keeps
            handle_commit() from running flat out against this."""
            fd = 99

            def add_watch(self, path, mask):
                pass

            def read_events(self):
                return ['event']

        # Ready on every odd call, not-ready on every even one, so each drain
        # loop (pre- and post-handle_commit) drains exactly one queued event
        # and then exits rather than spinning forever on an always-ready fd.
        select_calls = {'n': 0}

        def fake_select(*_args, **_kwargs):
            select_calls['n'] += 1
            return ([1], [], []) if select_calls['n'] % 2 else ([], [], [])

        with unittest.mock.patch.object(module, 'handle_commit', fake_handle_commit), \
             unittest.mock.patch.object(module.select, 'select', fake_select), \
             unittest.mock.patch.object(module.time, 'monotonic', fake_monotonic), \
             unittest.mock.patch.object(module.time, 'sleep', fake_sleep):
            with self.assertRaises(self.StopWatching):
                module.watch_forever(inotify=AlwaysReadyInotify(), debounce_seconds=0,
                                     min_interval_seconds=5)

        self.assertEqual(len(calls), 3)
        # The clock only moves via fake_sleep, so consecutive calls at least
        # min_interval_seconds apart on the fake clock proves the loop
        # actually waited rather than calling straight through.
        self.assertGreaterEqual(calls[1] - calls[0], 5)
        self.assertGreaterEqual(calls[2] - calls[1], 5)


if __name__ == '__main__':
    unittest.main()
