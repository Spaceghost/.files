"""Integration checks for the .files Git sync worker."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / ".bin" / "spaceghost-sync"


def git(*args, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote, self.writer, self.reader = (root / name for name in ("remote.git", "writer", "reader"))
        git("init", "--bare", "-b", "base", str(self.remote))
        git("clone", str(self.remote), str(self.writer))
        for repo in (self.writer,):
            git("config", "user.name", "Sync Test", cwd=repo)
            git("config", "user.email", "sync@example.test", cwd=repo)
        (self.writer / "config").write_text("initial\n")
        git("add", "config", cwd=self.writer)
        git("commit", "-m", "initial", cwd=self.writer)
        git("push", "origin", "base", cwd=self.writer)
        git("clone", str(self.remote), str(self.reader))
        git("config", "user.name", "Sync Test", cwd=self.reader)
        git("config", "user.email", "sync@example.test", cwd=self.reader)
        self.state = root / "state"

    def sync(self, repo, check=True):
        self.assertTrue(SCRIPT.is_file(), "spaceghost-sync is missing")
        env = dict(os.environ, SPACEGHOST_SYNC_REPO=str(repo), SPACEGHOST_SYNC_STATE=str(self.state),
                   SPACEGHOST_SYNC_NO_RELOAD="1", GIT_TERMINAL_PROMPT="0")
        return subprocess.run([str(SCRIPT), "run"], env=env, capture_output=True, text=True, check=check)

    def test_pulls_a_commit_without_touching_unrelated_local_edits(self):
        (self.reader / "local").write_text("unfinished\n")
        (self.writer / "config").write_text("latest\n")
        git("commit", "-am", "new config", cwd=self.writer)
        git("push", "origin", "base", cwd=self.writer)

        self.sync(self.reader)

        self.assertEqual((self.reader / "config").read_text(), "latest\n")
        self.assertEqual((self.reader / "local").read_text(), "unfinished\n")

    def test_pushes_a_local_commit(self):
        (self.reader / "config").write_text("from reader\n")
        git("commit", "-am", "reader config", cwd=self.reader)

        self.sync(self.reader)

        self.assertEqual(git("rev-parse", "HEAD", cwd=self.reader),
                         git("rev-parse", "refs/heads/base", cwd=self.remote))

    def test_keeps_conflicting_uncommitted_edit_intact(self):
        (self.reader / "config").write_text("unfinished\n")
        (self.writer / "config").write_text("remote\n")
        git("commit", "-am", "remote config", cwd=self.writer)
        git("push", "origin", "base", cwd=self.writer)

        result = self.sync(self.reader, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.reader / "config").read_text(), "unfinished\n")
        self.assertEqual(git("status", "--short", cwd=self.reader), "M config")

    def test_rebases_and_publishes_independent_commits(self):
        (self.reader / "local").write_text("reader\n")
        git("add", "local", cwd=self.reader)
        git("commit", "-m", "reader work", cwd=self.reader)
        (self.writer / "config").write_text("writer\n")
        git("commit", "-am", "writer work", cwd=self.writer)
        git("push", "origin", "base", cwd=self.writer)

        self.sync(self.reader)

        self.assertEqual((self.reader / "config").read_text(), "writer\n")
        self.assertEqual((self.reader / "local").read_text(), "reader\n")
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.reader),
                         git("rev-parse", "refs/heads/base", cwd=self.remote))


if __name__ == "__main__":
    unittest.main()
