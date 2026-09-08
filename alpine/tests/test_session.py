"""Session startup tests use fake desktop services in an isolated HOME."""
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
SESSION = REPO / 'alpine/desktop/.local/bin/mbp-intel-session'


class SessionTests(unittest.TestCase):
    def test_concurrent_reload_starts_services_once(self):
        with tempfile.TemporaryDirectory(prefix='mbp-intel-session-test-') as directory:
            root = Path(directory)
            local_bin = root / '.local/bin'
            local_bin.mkdir(parents=True)
            services = ['pipewire', 'wireplumber', 'pipewire-pulse', 'swaync', 'swayidle', 'waybar']
            for service in services:
                path = local_bin / service
                # Exercise startup locking without paying interpreter startup
                # costs for every fake service when the host is under load.
                path.write_text('#!/bin/sh\nsleep 0.2\n'
                                'printf \'%s\\n\' "$$" >> '
                                + shlex.quote(str(root / service)) + '\nsleep 10\n')
                path.chmod(0o755)
            pgrep = local_bin / 'pgrep'
            pgrep.write_text('#!/bin/sh\nfor name do :; done\n'
                             'case "$name" in *polkit-gnome*) exit 0;; esac\n'
                             '[ -e ' + shlex.quote(directory) + '/"$name" ]\n')
            pgrep.chmod(0o755)
            for name in ['dbus-update-activation-environment', 'mbp-intel-wallpaper']:
                (local_bin / name).write_text('#!/bin/sh\nexit 0\n')
                (local_bin / name).chmod(0o755)
            (local_bin / 'dbus-update-activation-environment').write_text(
                '#!/bin/sh\nprintf \'%s\\n\' started >> '
                + shlex.quote(str(root / 'setup-runs')) + '\n')
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
