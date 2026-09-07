"""A successful unexpected HTTP response must never count as firewall denial."""
import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('verify_host', str(Path(__file__).with_name('verify-host')))
spec = importlib.util.spec_from_loader(loader.name, loader)
probe = importlib.util.module_from_spec(spec)
loader.exec_module(probe)


class ProbeVerdictTests(unittest.TestCase):
    def result(self, code, body='', connections=None):
        if connections is None:
            connections = 1 if code == 0 else 0
        output = body + f'\nOLDBOOK_CONNECTS:{connections}'
        with patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, output, '')):
            return probe.curl('192.0.2.2', 443, uid=1000)

    def test_successful_unexpected_response_is_an_error_not_denial(self):
        with self.assertRaisesRegex(RuntimeError, 'HTTP succeeded'):
            self.result(0, '<html>Another server</html>')

    def test_expected_response_is_allowed(self):
        self.assertTrue(self.result(0, 'OLDBOOK_PACKET_PROBE\n'))

    def test_timeout_is_denied(self):
        self.assertFalse(self.result(28))

    def test_timeout_after_tcp_connect_is_inconclusive(self):
        with self.assertRaisesRegex(RuntimeError, 'TCP connected'):
            self.result(28, connections=1)

    def test_connection_refusal_is_a_fixture_error(self):
        with self.assertRaisesRegex(RuntimeError, 'unexpectedly'):
            self.result(7)
