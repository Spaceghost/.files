"""Bounded rtnetlink decoding with synthetic datagrams only."""
import importlib
import socket
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'root/usr/local/lib'))
try:
    link = importlib.import_module('privacyctl_runtime.link')
except ModuleNotFoundError:
    link = None


def attribute(kind, value):
    raw = struct.pack('=HH', len(value) + 4, kind) + value
    return raw + b'\0' * (-len(raw) % 4)


def packet(alias=b'prior\xff alias', *, name=b'wlan0', index=7, sequence=12, port=99,
           extra=b'', omit_alias=False):
    body = struct.pack('=BBHiII', 0, 0, 1, index, 0, 0)
    body += attribute(3, name + b'\0')
    if not omit_alias:
        body += attribute(20, alias + b'\0')
    body += extra
    return struct.pack('=IHHII', len(body) + 16, 16, 0, sequence, port) + body


class FakeSocket:
    def __init__(self, response=None):
        self.response = response
        self.closed = False
        self.sent = None
        self.flags = 0
        self.sender = (0, 0)

    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def bind(self, address): self.bound = address
    def getsockname(self): return (99, 0)
    def settimeout(self, timeout): self.timeout = timeout
    def sendto(self, data, address):
        self.sent = data
        self.destination = address
        return len(data)
    def recvmsg(self, size):
        sequence = struct.unpack('=IHHII', self.sent[:16])[3]
        return self.response or packet(sequence=sequence), [], self.flags, self.sender


class LinkTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(link, 'link primitive not implemented')

    def decode(self, data):
        return link.decode_link(data, sequence=12, port=99, interface='wlan0')

    def test_raw_alias_roundtrips_and_absent_means_empty(self):
        self.assertEqual(self.decode(packet()).alias, b'prior\xff alias')
        value = self.decode(packet(omit_alias=True))
        self.assertEqual((value.ifindex, value.name, value.alias), (7, 'wlan0', b''))

    def test_name_index_sequence_sender_header_and_duplicates_refuse(self):
        for data in [packet(name=b'other'), packet(index=0), packet(sequence=11),
                     packet(port=88), packet(extra=attribute(3, b'wlan0\0')),
                     packet(extra=attribute(20, b'other\0')), packet() + packet()]:
            with self.subTest(data=data[:20]), self.assertRaises(link.LinkError):
                self.decode(data)

    def test_alias_bounds_nul_and_malformed_lengths_refuse(self):
        for data in [packet(alias=b'x' * 256), packet(alias=b'a\0b'), packet()[:-1],
                     b'x' * 65537, packet(extra=b'\x03\x00\x63\x00')]:
            with self.subTest(length=len(data)), self.assertRaises(link.LinkError):
                self.decode(data)

    def test_kernel_error_refuses(self):
        raw = struct.pack('=IHHIIi', 20, 2, 0, 12, 99, -19)
        with self.assertRaises(link.LinkError): self.decode(raw)

    def test_query_only_getlink_bounded_and_closes_socket(self):
        fake = FakeSocket()
        with patch.object(link.socket, 'socket', return_value=fake) as opened:
            value = link.read_link('wlan0', deadline=100, clock=lambda: 99.5)
        opened.assert_called_once_with(socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE)
        header = struct.unpack('=IHHII', fake.sent[:16])
        self.assertEqual(header[1:3], (18, 1))
        self.assertEqual(fake.destination, (0, 0))
        self.assertLessEqual(fake.timeout, .5)
        self.assertTrue(fake.closed)
        self.assertEqual(value.alias, b'prior\xff alias')

    def test_truncation_foreign_sender_cancel_and_deadline_refuse(self):
        for flags, sender in [(socket.MSG_TRUNC, (0, 0)), (0, (123, 0))]:
            fake = FakeSocket(); fake.flags, fake.sender = flags, sender
            with patch.object(link.socket, 'socket', return_value=fake):
                with self.assertRaises(link.LinkError):
                    link.read_link('wlan0', deadline=100, clock=lambda: 99)
            self.assertTrue(fake.closed)
        with patch.object(link.socket, 'socket', side_effect=AssertionError('late socket')):
            with self.assertRaises(link.LinkError):
                link.read_link('wlan0', deadline=100, clock=lambda: 101)
            with self.assertRaisesRegex(RuntimeError, 'cancel'):
                link.read_link('wlan0', deadline=100, check=lambda: (_ for _ in ()).throw(RuntimeError('cancel')))


if __name__ == '__main__': unittest.main()
