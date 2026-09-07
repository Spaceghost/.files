import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "alpine/desktop/.local/bin/oldbook-video-background"


class VideoBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base = Path(self.tempdir.name)
        self.runtime = self.base / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.record = self.base / "mpvpaper-argv.json"
        self.mpvpaper = self._executable(
            "mpvpaper",
            """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

Path(os.environ['FAKE_MVPAPER_RECORD']).write_text(json.dumps(sys.argv[1:]))
while True:
    time.sleep(1)
""",
        )
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.base / "home"),
                "XDG_RUNTIME_DIR": str(self.runtime),
                "FAKE_MVPAPER_RECORD": str(self.record),
                "OLDBOOK_VIDEO_MPV_PAPER": str(self.mpvpaper),
            }
        )
        Path(self.env["HOME"]).mkdir()
        self.addCleanup(
            lambda: self._run("stop") if SCRIPT.exists() else None
        )

    def _executable(self, name, contents):
        path = self.base / name
        path.write_text(contents)
        path.chmod(0o755)
        return path

    def _run(self, *arguments):
        return subprocess.run(
            [str(SCRIPT), *map(str, arguments)],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=8,
        )

    def _state(self):
        return json.loads(
            (self.runtime / "oldbook/video-background/state.json").read_text()
        )

    def _wait_dead(self, pid):
        for _ in range(80):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.025)
        self.fail(f"owned mpvpaper process {pid} did not stop")

    def test_start_and_stop_use_one_owned_group_and_literal_arguments(self):
        sentinel = self.base / "must-not-exist"
        video = self.base / "clip $(touch must-not-exist); name\nline.y4m"
        video.write_bytes(b"YUV4MPEG2 W2 H2 F1:1 Ip A1:1 C420jpeg\n")

        started = self._run(video)
        self.assertEqual(started.returncode, 0, started.stderr)
        state = self._state()
        pid = state["pid"]
        self.assertEqual(state["pgid"], pid)
        self.assertFalse(sentinel.exists())
        self.assertEqual(
            json.loads(self.record.read_text()),
            [
                "--layer",
                "bottom",
                "--mpv-options",
                (
                    "config=no no-audio loop-file=inf hwdec=auto-safe "
                    "input-default-bindings=no input-cursor=no osc=no terminal=no"
                ),
                "ALL",
                str(video.resolve()),
            ],
        )

        unrelated = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(lambda: self._terminate(unrelated))
        stopped = self._run("stop")
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self._wait_dead(pid)
        self.assertIsNone(unrelated.poll())
        self.assertFalse(
            (self.runtime / "oldbook/video-background/state.json").exists()
        )

    def test_replacement_stops_only_the_previously_recorded_group(self):
        first = self.base / "first.y4m"
        second = self.base / "second.y4m"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        self.assertEqual(self._run(first).returncode, 0)
        old_pid = self._state()["pid"]

        replaced = self._run(second)
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        new_pid = self._state()["pid"]
        self.assertNotEqual(old_pid, new_pid)
        self._wait_dead(old_pid)
        self.assertEqual(json.loads(self.record.read_text())[-1], str(second.resolve()))
        self.addCleanup(lambda: self._run("stop"))

    def test_accepts_explicit_https_and_rejects_unsafe_or_missing_sources(self):
        accepted = self._run("https://media.example/video.mp4?quality=720p")
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(
            json.loads(self.record.read_text())[-1],
            "https://media.example/video.mp4?quality=720p",
        )
        self.assertEqual(self._run("stop").returncode, 0)

        for source in (
            "http://media.example/video.mp4",
            "https://user:password@media.example/video.mp4",
            "https://[invalid-host/video.mp4",
            "https://media.example/video.mp4\nquit",
            str(self.base / "missing.mp4"),
        ):
            with self.subTest(source=repr(source)):
                rejected = self._run(source)
                self.assertEqual(rejected.returncode, 2, rejected.stderr)
                self.assertNotIn("Traceback", rejected.stderr)
                self.assertFalse(
                    (self.runtime / "oldbook/video-background/state.json").exists()
                )

    def test_picker_passes_an_explicit_selection_through_validation(self):
        videos = Path(self.env["HOME"]) / "Videos"
        videos.mkdir()
        selected = videos / "picked clip.webm"
        selected.write_bytes(b"video")
        fuzzel_input = self.base / "fuzzel-input.txt"
        fuzzel = self._executable(
            "fuzzel",
            """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

Path(os.environ['FAKE_FUZZEL_INPUT']).write_text(sys.stdin.read())
print(os.environ['FAKE_FUZZEL_SELECTION'])
""",
        )
        self.env.update(
            {
                "FAKE_FUZZEL_INPUT": str(fuzzel_input),
                "FAKE_FUZZEL_SELECTION": str(selected),
                "OLDBOOK_VIDEO_FUZZEL": str(fuzzel),
            }
        )

        picked = self._run("picker")
        self.assertEqual(picked.returncode, 0, picked.stderr)
        self.assertIn(str(selected), fuzzel_input.read_text().splitlines())
        self.assertEqual(json.loads(self.record.read_text())[-1], str(selected.resolve()))
        self.addCleanup(lambda: self._run("stop"))

    @staticmethod
    def _terminate(process):
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
