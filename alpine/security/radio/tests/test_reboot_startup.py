"""Real temp journal and ownership locks; no radio, process or resolver commands."""
from contextlib import nullcontext
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_journal import record
from privacyctl_runtime import adapter, dhcp, ipc, journal


@unittest.skipUnless(os.geteuid() == 0, 'root-private temporary ownership locks required')
class RebootStartupTests(unittest.TestCase):
    def test_old_boot_empty_intent_retires_before_readiness_with_owner_and_dhcp_locks_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runtime = root / 'run'; state = root / 'state'
            state.mkdir(mode=0o700)
            store = journal.Journal(state); store.write(record())
            events = []
            legacy = SimpleNamespace(RadioLock=lambda **kwargs: nullcontext(),
                                     clear_session=lambda: None)
            backend = adapter.NativeNetwork()
            native = adapter.NativeAdapter(legacy, runtime=runtime, state=state,
                system=SimpleNamespace(block_all=lambda: events.append('blocked')), backend=backend)
            server = ipc.Server(runtime); manager = dhcp.DHCPManager(runtime)
            try:
                server.acquire(); manager.acquire()
                self.assertFalse((runtime / 'owner.sock').exists())
                with patch.object(backend, '_run', side_effect=AssertionError('native execution forbidden')):
                    native.prepare_recovery(check=lambda: None)
                self.assertTrue(events)
                self.assertIsNone(journal.Journal(state).read())
                self.assertFalse((runtime / 'owner.sock').exists())
                other = ipc.Server(runtime)
                try:
                    with self.assertRaises(ipc.IPCError): other.acquire()
                finally: other.close()
                manager.journal = native.journal
                server.listen()
                self.assertTrue((runtime / 'owner.sock').is_socket())
            finally:
                manager.close(); server.close()
