"""History integration uses a real cliphist database, with isolated UI/clipboard sinks."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "alpine/desktop/.local/bin/mbp-intel-clipboard"


@unittest.skipUnless(shutil.which("cliphist"), "cliphist is required")
class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_STATE_HOME=str(self.root / "state"),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_RUNTIME_DIR=str(self.root / "run"),
                        PATH=str(self.bin) + ":" + os.environ["PATH"])
        self.env.pop("CLIPHIST_DB_PATH", None)
        self.env.pop("CLIPBOARD_STATE", None)
        self.env.pop("CLIPHIST_CONFIG_PATH", None)
        self.sink = self.root / "copied"
        self.fake("wl-copy", 'import sys\nfrom pathlib import Path\n'
                  + f'Path({str(self.sink)!r}).write_bytes(sys.stdin.buffer.read())\n')
        self.fake("mbp-intel-fuzzel", 'import sys\nrows=sys.stdin.buffer.readlines()\n'
                  'sys.stdout.buffer.write(rows[0] if rows else b"")\n')

    def fake(self, name, body):
        path = self.bin / name
        path.write_text("#!/usr/bin/python3\n" + body)
        path.chmod(0o755)

    def run_helper(self, command, data=b"", **env):
        result = subprocess.run(["python3", str(HELPER), command], input=data,
                                env=dict(self.env, **env), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return result.stdout

    def test_recall_preserves_multiline_unicode_and_trailing_newlines(self):
        payload = "  clipboard café\nsecond line\n\n".encode()
        self.run_helper("store", payload)
        self.run_helper("pick")
        self.assertEqual(self.sink.read_bytes(), payload)

    def test_recall_preserves_binary_bytes(self):
        payload = b"\x89PNG\r\n\x1a\n\x00\xffclipboard-fixture"
        self.run_helper("store", payload)
        self.run_helper("pick")
        self.assertEqual(self.sink.read_bytes(), payload)

    def test_sensitive_and_empty_events_do_not_enter_history(self):
        for state in ("sensitive", "nil", "clear"):
            self.run_helper("store", b"synthetic-secret", CLIPBOARD_STATE=state)
        self.assertEqual(self.run_helper("list"), b"")

    def test_cancel_does_not_replace_clipboard(self):
        self.sink.write_bytes(b"previous clipboard")
        self.run_helper("store", b"history item")
        self.fake("mbp-intel-fuzzel", "import sys\nsys.exit(1)\n")
        self.run_helper("pick")
        self.assertEqual(self.sink.read_bytes(), b"previous clipboard")

    def test_failed_decode_does_not_clear_clipboard(self):
        self.sink.write_bytes(b"previous clipboard")
        self.run_helper("store", b"history item")
        self.fake("mbp-intel-fuzzel", 'print("999999\\tmissing entry")\n')
        result = subprocess.run(["python3", str(HELPER), "pick"], env=self.env,
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.sink.read_bytes(), b"previous clipboard")

    def test_delete_removes_only_selected_entry_and_clear_empties_history(self):
        self.run_helper("store", b"older")
        self.run_helper("store", b"newer")
        self.run_helper("delete")
        remaining = self.run_helper("list")
        self.assertIn(b"older", remaining)
        self.assertNotIn(b"newer", remaining)
        self.run_helper("clear")
        self.assertEqual(self.run_helper("list"), b"")

    def test_database_is_private_and_history_is_deduplicated(self):
        self.run_helper("store", b"same")
        self.run_helper("store", b"same")
        self.assertEqual(len(self.run_helper("list").splitlines()), 1)
        files = list((self.root / "state").rglob("*.db"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_mode & 0o077, 0)
        self.assertEqual(files[0].parent.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
