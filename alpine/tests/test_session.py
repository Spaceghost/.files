"""Session startup tests use fake desktop services in an isolated HOME."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
SESSION = REPO / 'alpine/desktop/.local/bin/oldbook-session'


class SessionTests(unittest.TestCase):
    def test_concurrent_reload_starts_services_once(self):
        with tempfile.TemporaryDirectory(prefix='oldbook-session-test-') as directory:
            root = Path(directory)
            local_bin = root / '.local/bin'
            local_bin.mkdir(parents=True)
            services = ['pipewire', 'wireplumber', 'pipewire-pulse', 'swaync', 'swayidle', 'waybar']
            for service in services:
                path = local_bin / service
                path.write_text('#!/usr/bin/python3\nimport os,time\n'
                                'time.sleep(.2)\n'
                                f'with open({str(root / service)!r}, "a") as f: f.write(str(os.getpid())+"\\n")\n'
                                'time.sleep(10)\n')
                path.chmod(0o755)
            pgrep = local_bin / 'pgrep'
            pgrep.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n'
                             'name=sys.argv[-1]\n'
                             'if "polkit-gnome" in name: sys.exit(0)\n'
                             f'sys.exit(0 if (Path({directory!r}) / name).exists() else 1)\n')
            pgrep.chmod(0o755)
            for name in ['dbus-update-activation-environment', 'oldbook-wallpaper']:
                (local_bin / name).write_text('#!/bin/sh\nexit 0\n')
                (local_bin / name).chmod(0o755)
            (local_bin / 'dbus-update-activation-environment').write_text(
                '#!/bin/sh\nprintf started\\n >>' + str(root / 'setup-runs') + '\n')
            env = dict(os.environ, HOME=directory, XDG_RUNTIME_DIR=directory,
                       DBUS_SESSION_BUS_ADDRESS='unix:path=' + directory + '/unused')
            clients = []
            try:
                clients = [subprocess.Popen([str(SESSION)], env=env, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, start_new_session=True)
                           for _ in range(2)]
                for client in clients:
                    self.assertEqual(client.wait(timeout=4), 0)
                time.sleep(.4)
                for name in services:
                    self.assertEqual(len((root / name).read_text().splitlines()), 1, name)
                # Background services must not retain the startup lock.
                again = subprocess.Popen([str(SESSION)], env=env, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
                clients.append(again)
                self.assertEqual(again.wait(timeout=4), 0)
                self.assertEqual((root / 'setup-runs').read_text().count('started'), 2)
            finally:
                for client in clients:
                    try:
                        os.killpg(client.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    client.wait()


if __name__ == '__main__':
    unittest.main()
