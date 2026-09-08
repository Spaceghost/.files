"""Firewall GUI startup uses temporary runlevels and fake desktop processes."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from unittest import mock


HELPER = Path(__file__).resolve().parents[1] / "desktop/.local/bin/mbp-intel-firewall-ui"
loader = importlib.machinery.SourceFileLoader("firewall_ui", str(HELPER))
spec = importlib.util.spec_from_loader(loader.name, loader)
ui = importlib.util.module_from_spec(spec)
loader.exec_module(ui)


class FirewallUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mbp-intel-firewall-ui-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runlevels = self.root / "runlevels"
        (self.runlevels / "boot").mkdir(parents=True)
        self.initd = self.root / "init.d"
        self.initd.mkdir()
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        for name in ("mbp-intel-firewall", "opensnitchd"):
            (self.initd / name).write_text("#!/bin/sh\nexit 0\n")
        for name, value in (("RUNLEVELS", self.runlevels), ("INITD", self.initd), ("PROC", self.proc)):
            patch = mock.patch.object(ui, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.runtime)})
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(ui.shutil, "which", return_value="/usr/bin/opensnitch-ui")
        patch.start()
        self.addCleanup(patch.stop)

    def enable(self, name=None):
        for service in (name,) if name else ("mbp-intel-firewall", "opensnitchd"):
            (self.runlevels / "boot" / service).symlink_to(self.initd / service)

    def test_disabled_or_partially_enabled_setup_does_nothing(self):
        with mock.patch.object(ui.subprocess, "call") as launch:
            self.assertEqual(ui.main(), 0)
            self.enable("mbp-intel-firewall")
            self.assertEqual(ui.main(), 0)
            launch.assert_not_called()
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_service_names_without_valid_runlevel_links_do_not_enable(self):
        self.enable("mbp-intel-firewall")
        (self.runlevels / "boot" / "opensnitchd").write_text("not an OpenRC link")
        self.assertFalse(ui.services_enabled())
        (self.runlevels / "boot" / "opensnitchd").unlink()
        (self.runlevels / "boot" / "opensnitchd").symlink_to(self.root / "missing")
        self.assertFalse(ui.services_enabled())

    def test_enabled_setup_launches_background_gui_with_private_socket(self):
        self.enable()
        with mock.patch.object(ui.subprocess, "call", return_value=0) as launch:
            self.assertEqual(ui.main(), 0)
        self.assertEqual(launch.call_args.args[0], ["/usr/bin/opensnitch-ui", "--background", "--socket",
                         "unix://" + str(self.runtime / "opensnitch/osui.sock")])
        self.assertEqual((self.runtime / "opensnitch").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.runtime / "opensnitch/ui-startup.lock").stat().st_mode & 0o777, 0o600)

    def test_existing_gui_is_not_restarted_focused_or_notified(self):
        self.enable()
        process = self.proc / "123"
        process.mkdir()
        (process / "cmdline").write_bytes(b"/usr/bin/python3\0/usr/bin/opensnitch-ui\0")
        with mock.patch.object(ui.subprocess, "call") as launch:
            self.assertEqual(ui.main(), 0)
            launch.assert_not_called()

    def test_listening_grpc_socket_suppresses_duplicate_without_unlink(self):
        self.enable()
        parent = self.runtime / "opensnitch"
        parent.mkdir(mode=0o700)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            path = parent / "osui.sock"
            listener.bind(str(path))
            listener.listen(1)
            inode = path.stat().st_ino
            with mock.patch.object(ui.subprocess, "call") as launch:
                self.assertEqual(ui.main(), 0)
                launch.assert_not_called()
            self.assertEqual(path.stat().st_ino, inode)

    def test_unsafe_runtime_permissions_owner_and_symlink_are_rejected(self):
        self.enable()
        self.runtime.chmod(0o777)
        with self.assertRaises(ValueError):
            ui.main()
        self.runtime.chmod(0o700)
        with mock.patch.object(ui.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(ValueError):
                ui.main()
        other = self.root / "other"
        other.mkdir(mode=0o755)
        (self.runtime / "opensnitch").symlink_to(other, target_is_directory=True)
        with self.assertRaises(OSError):
            ui.main()
        self.assertEqual(other.stat().st_mode & 0o777, 0o755)

    def test_socket_file_and_symlink_lock_are_preserved_and_rejected(self):
        self.enable()
        parent = self.runtime / "opensnitch"
        parent.mkdir(mode=0o700)
        path = parent / "osui.sock"
        path.write_text("must survive")
        with self.assertRaises(ValueError):
            ui.main()
        self.assertEqual(path.read_text(), "must survive")
        path.unlink()
        (parent / "ui-startup.lock").unlink()
        target = self.root / "lock-target"
        target.write_text("must survive")
        (parent / "ui-startup.lock").symlink_to(target)
        with self.assertRaises(OSError):
            ui.main()
        self.assertEqual(target.read_text(), "must survive")

    def test_concurrent_helpers_start_one_gui_and_hold_lock_for_its_lifetime(self):
        self.enable()
        binary = self.root / "bin"
        binary.mkdir()
        fake = binary / "opensnitch-ui"
        record = self.root / "started.jsonl"
        release = self.root / "release"
        fake.write_text("#!/usr/bin/python3\nimport json,os,sys,time\nfrom pathlib import Path\n"
                        f"with open({str(record)!r},'a') as f: f.write(json.dumps(sys.argv)+'\\n')\n"
                        f"while not Path({str(release)!r}).exists(): time.sleep(.02)\n")
        fake.chmod(0o755)
        wrapper = self.root / "invoke.py"
        wrapper.write_text("import importlib.machinery,importlib.util\nfrom pathlib import Path\n"
                           f"loader=importlib.machinery.SourceFileLoader('ui',{str(HELPER)!r})\n"
                           "spec=importlib.util.spec_from_loader(loader.name,loader)\n"
                           "ui=importlib.util.module_from_spec(spec);loader.exec_module(ui)\n"
                           f"ui.RUNLEVELS=Path({str(self.runlevels)!r});ui.INITD=Path({str(self.initd)!r})\n"
                           f"ui.PROC=Path({str(self.proc)!r})\nraise SystemExit(ui.main())\n")
        env = dict(os.environ, PATH=str(binary) + ":/usr/bin:/bin", XDG_RUNTIME_DIR=str(self.runtime))
        children = []
        try:
            children = [subprocess.Popen(["/usr/bin/python3", str(wrapper)], env=env,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         start_new_session=True) for _ in range(2)]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not record.exists():
                time.sleep(0.02)
            self.assertTrue(record.exists(), "fake GUI was never launched")
            again = subprocess.run(["/usr/bin/python3", str(wrapper)], env=env,
                                   capture_output=True, timeout=3)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(len(record.read_text().splitlines()), 1)
            release.touch()
            for child in children:
                self.assertEqual(child.wait(timeout=3), 0)
        finally:
            release.touch()
            for child in children:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()


if __name__ == "__main__":
    unittest.main()
