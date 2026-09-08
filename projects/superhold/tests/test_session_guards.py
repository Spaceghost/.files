# SPDX-License-Identifier: GPL-3.0-or-later
"""Lock-authority failures must not be mistaken for an unlocked session."""
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from superhold import service


def reply(stdout='', stderr='', code=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


class SessionAuthorityTests(unittest.TestCase):
    def test_missing_dbus_client_with_configured_bus_denies_overlay(self):
        with patch.dict(os.environ, {'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/synthetic'}, clear=True), \
                patch.object(service.subprocess, 'run', side_effect=FileNotFoundError()):
            self.assertTrue(service.screensaver_locked())

    def test_no_authorities_is_reported_explicitly(self):
        with patch.dict(os.environ, {'DISPLAY': ':123'}, clear=True):
            status = service.probe_session('x11', Path('/unused'))
        self.assertIs(status.get('lock_authority'), False)
        self.assertTrue(status['active'])

    def test_existing_screensaver_false_is_a_positive_lock_authority(self):
        def run(argv, **_kwargs):
            if argv[-1] == 'string:org.gnome.ScreenSaver':
                return reply(stderr='NameHasNoOwner', code=1)
            if 'org.freedesktop.DBus.GetNameOwner' in argv:
                return reply('method return\n string ":1.25"\n')
            self.assertIn('--dest=:1.25', argv)
            return reply('method return\n boolean false\n')
        with patch.dict(os.environ, {'DISPLAY': ':123',
                                     'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/synthetic'}, clear=True), \
                patch.object(service.subprocess, 'run', side_effect=run):
            status = service.probe_session('x11', Path('/unused'))
        self.assertIs(status.get('lock_authority'), True)
        self.assertFalse(status['locked'])

    def test_absent_screensavers_do_not_claim_lock_authority(self):
        with patch.dict(os.environ, {'DISPLAY': ':123',
                                     'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/synthetic'}, clear=True), \
                patch.object(service.subprocess, 'run',
                             return_value=reply(stderr='NameHasNoOwner', code=1)):
            status = service.probe_session('x11', Path('/unused'))
        self.assertIs(status.get('lock_authority'), False)

    def test_logind_requires_explicit_locked_hint(self):
        env = {'DISPLAY': ':123', 'XDG_SESSION_ID': 'synthetic'}
        for hint, authority, locked in (('LockedHint=no\n', True, False),
                                        ('LockedHint=yes\n', True, True), ('', False, True)):
            with self.subTest(hint=hint), patch.dict(os.environ, env, clear=True), \
                    patch.object(service.subprocess, 'run', return_value=reply(
                        'Active=yes\nState=active\nType=x11\n' + hint)):
                status = service.probe_session('x11', Path('/unused'))
            self.assertIs(status.get('lock_authority'), authority)
            self.assertIs(status['locked'], locked)

    def test_guard_exposes_only_confirmed_lock_authority(self):
        guard = service.GraphicalSessionGuard(
            Path('/unused'), Path('/unused'),
            activity_probe=lambda: {'active': True, 'locked': False, 'lock_authority': True},
            lock_probe=lambda *_args: False)
        try:
            self.assertIs(getattr(guard, 'lock_authority', None), False)
            deadline = time.monotonic() + 1
            while not guard.allows_overlay(time.monotonic()) and time.monotonic() < deadline:
                time.sleep(.001)
            self.assertIs(guard.lock_authority, True)
        finally:
            guard.close()


if __name__ == '__main__':
    unittest.main()
