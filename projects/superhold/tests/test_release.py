# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("release", Path(__file__).resolve().parents[1] / "tools/make-release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for name in release.REQUIRED:
            (self.source / name).write_text(f"content for {name}\n")
        for name in ("bin", "data", "examples", "superhold", "native", "tests", "tools"):
            (self.source / name).mkdir()
        (self.source / "superhold/__init__.py").write_text("VERSION = '0.1.0'\n")
        (self.source / "SOURCE_MANIFEST").write_text("\n".join((*release.REQUIRED, "superhold/__init__.py")) + "\n")

    def test_archive_is_independent_of_mtimes_and_output_path(self):
        first = self.root / "first.tar.gz"
        second = self.root / "second.tar.gz"
        release.make_release(self.source, first)
        import os
        for path in self.source.rglob("*"):
            os.utime(path, (42, 42))
        release.make_release(self.source, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(first) as archive:
            members = archive.getmembers()
            self.assertEqual([m.name for m in members], sorted(m.name for m in members))
            self.assertTrue(all(m.uid == m.gid == 0 and m.mtime == release.EPOCH for m in members))

    def test_secret_and_cache_files_are_excluded(self):
        (self.source / "auth.json").write_text("secret")
        cache = self.source / "superhold/__pycache__"
        cache.mkdir()
        (cache / "x.pyc").write_bytes(b"compiled")
        (self.source / "tools/.credentials").write_text("secret")
        (self.source / "tools/auth.json").write_text("secret")
        (self.source / "native/build").mkdir()
        (self.source / "native/build/CMakeCache.txt").write_text("local build path")
        names = [p.relative_to(self.source).as_posix() for p in release.source_files(self.source)]
        self.assertNotIn("auth.json", names)
        self.assertNotIn("tools/.credentials", names)
        self.assertNotIn("tools/auth.json", names)
        self.assertNotIn("native/build/CMakeCache.txt", names)
        self.assertFalse(any("__pycache__" in p for p in names))

    def test_symlinks_are_rejected_and_existing_archive_preserved(self):
        destination = self.root / "release.tar.gz"
        destination.write_bytes(b"existing")
        (self.source / "tools/escape").symlink_to("/etc/passwd")
        with (self.source / "SOURCE_MANIFEST").open("a") as stream:
            stream.write("tools/escape\n")
        with self.assertRaises(ValueError):
            release.make_release(self.source, destination)
        self.assertEqual(destination.read_bytes(), b"existing")

    def test_output_cannot_replace_source(self):
        with self.assertRaises(ValueError):
            release.make_release(self.source, self.source / "LICENSE")

    def test_traversal_and_symlinked_directories_are_rejected(self):
        with (self.source / "SOURCE_MANIFEST").open("a") as stream:
            stream.write("../outside\n")
        with self.assertRaises(ValueError):
            release.source_files(self.source)
        (self.source / "SOURCE_MANIFEST").write_text("\n".join(release.REQUIRED) + "\ntools/link/LICENSE\n")
        (self.source / "tools/link").symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            release.source_files(self.source)


if __name__ == "__main__":
    unittest.main()
