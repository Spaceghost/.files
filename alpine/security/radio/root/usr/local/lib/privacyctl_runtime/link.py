"""Read an exact link and its uninterpreted alias through bounded RTM_GETLINK.

No shell or NativeNetwork command is used, so writer registration can check link
identity without recursively creating another writer. Exclusive ownership must
exclude concurrent privileged renames/replacements throughout each mutation.
"""
from dataclasses import dataclass
import math
import re
import secrets
import socket
import struct
import time

MAX_BYTES = 65536


class LinkError(RuntimeError):
    """The link identity could not be established."""


def _require(condition, message):
    if not condition:
        raise LinkError(message)


def _name(value):
    _require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}', value, re.ASCII),
             'invalid fixed interface name')


@dataclass(frozen=True)
class LinkIdentity:
    ifindex: int
    name: str
    alias: bytes

    def __post_init__(self):
        _name(self.name)
        _require(type(self.ifindex) is int and 1 <= self.ifindex < 1 << 31, 'invalid link index')
        _require(type(self.alias) is bytes and len(self.alias) <= 255 and b'\0' not in self.alias,
                 'invalid raw link alias')


def decode_link(data, *, sequence, port, interface):
    """Decode one unicast GETLINK response; the transport verifies kernel sender."""
    _name(interface)
    _require(type(data) is bytes and 16 <= len(data) <= MAX_BYTES, 'invalid link response size')
    offset, found = 0, None
    while offset < len(data):
        _require(len(data) - offset >= 16, 'short netlink header')
        length, kind, flags, seq, pid = struct.unpack_from('=IHHII', data, offset)
        _require(16 <= length <= len(data) - offset and seq == sequence and pid == port,
                 'invalid link response header or identity')
        _require(not flags & (2 | 16), 'unexpected multipart/interrupted link response')
        body = data[offset + 16:offset + length]
        if kind == 2:
            _require(len(body) >= 4, 'short netlink error')
            code = struct.unpack_from('=i', body)[0]
            raise LinkError('kernel rejected link query: ' + str(code))
        _require(kind == 16 and len(body) >= 16 and found is None, 'unexpected or duplicate link reply')
        _, _, _, index, _, _ = struct.unpack_from('=BBHiII', body)
        attrs, cursor = {}, 16
        while cursor < len(body):
            _require(len(body) - cursor >= 4, 'short link attribute')
            size, tag = struct.unpack_from('=HH', body, cursor)
            _require(4 <= size <= len(body) - cursor, 'invalid link attribute length')
            if tag & 0x3fff in (3, 20):
                _require(tag in (3, 20) and tag not in attrs, 'invalid or duplicate link identity attribute')
                value = body[cursor + 4:cursor + size]
                _require(value.endswith(b'\0') and b'\0' not in value[:-1], 'invalid link string')
                attrs[tag] = value[:-1]
            cursor += (size + 3) & ~3
        _require(cursor == len(body) and attrs.get(3) == interface.encode('ascii'), 'link name changed')
        found = LinkIdentity(index, interface, attrs.get(20, b''))
        offset += (length + 3) & ~3
    _require(offset == len(data) and found is not None, 'incomplete link response')
    return found


def read_link(interface='wlan0', *, deadline, check=lambda: None, clock=time.monotonic):
    """Query only the fixed named link, under a total deadline and 250ms cap."""
    _name(interface)
    _require(type(deadline) in (int, float) and math.isfinite(deadline), 'invalid link deadline')

    def checkpoint():
        check()
        remaining = deadline - clock()
        _require(remaining > 0, 'link query deadline expired')
        return min(remaining, .25)

    checkpoint()
    try:
        with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, socket.NETLINK_ROUTE) as sock:
            sock.bind((0, 0))
            port = sock.getsockname()[0]
            sequence = secrets.randbelow((1 << 32) - 1) + 1
            raw_name = interface.encode('ascii') + b'\0'
            attr = struct.pack('=HH', len(raw_name) + 4, 3) + raw_name
            attr += b'\0' * (-len(attr) % 4)
            body = struct.pack('=BBHiII', socket.AF_UNSPEC, 0, 0, 0, 0, 0) + attr
            request = struct.pack('=IHHII', len(body) + 16, 18, 1, sequence, port) + body
            sock.settimeout(checkpoint())
            _require(sock.sendto(request, (0, 0)) == len(request), 'short link request')
            sock.settimeout(checkpoint())
            response, ancillary, flags, sender = sock.recvmsg(MAX_BYTES)
            checkpoint()
            _require(sender == (0, 0) and not ancillary and
                     not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC), 'untrusted or truncated link reply')
            return decode_link(response, sequence=sequence, port=port, interface=interface)
    except OSError as error:
        raise LinkError('link query failed') from error
