"""Pure, bounded DHCPv4 event validation; this module changes no host state.

An accepted lease is syntactically valid network data, not evidence that its
server or network is trusted. That decision belongs to the controller policy.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface
import re


_FIELDS = frozenset(('interface', 'ip', 'subnet', 'mask', 'router', 'dns', 'lease', 'serverid'))
_REQUIRED = frozenset(('interface', 'ip', 'lease', 'serverid'))
_INTERFACE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,14}', re.ASCII)
_DECIMAL = re.compile(r'[0-9]+', re.ASCII)
_MAX_FIELD = 256
_MAX_PAYLOAD = 1024
_MAX_LEASE = (1 << 32) - 1


def _interface(value: str) -> None:
    if not isinstance(value, str) or not _INTERFACE.fullmatch(value):
        raise ValueError('invalid interface name')


def _fields(values: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(values, Mapping):
        raise ValueError('lease event must be a mapping')
    if len(values) > len(_FIELDS):
        raise ValueError('lease event has too many fields')
    result = {}
    size = 0
    for key, value in values.items():
        if not isinstance(key, str) or key not in _FIELDS:
            raise ValueError('unknown lease event field')
        if not isinstance(value, str):
            raise ValueError('lease event fields must be strings')
        if len(value) > _MAX_FIELD:
            raise ValueError('lease event field is too large')
        if not value.isascii() or any(ord(char) < 32 or ord(char) > 126 for char in value):
            raise ValueError('lease event field contains non-printable or non-ASCII text')
        size += len(key) + len(value)
        if size > _MAX_PAYLOAD:
            raise ValueError('lease event payload is too large')
        result[key] = value
    if not _REQUIRED.issubset(result):
        raise ValueError('lease event is missing required fields')
    return result


def _decimal(value: str, minimum: int, maximum: int, field: str) -> int:
    if not _DECIMAL.fullmatch(value):
        raise ValueError(f'invalid {field}: expected decimal integer')
    number = int(value)
    if not minimum <= number <= maximum:
        raise ValueError(f'invalid {field}: integer outside allowed range')
    return number


def _address(value: str, field: str) -> IPv4Address:
    try:
        return IPv4Address(value)
    except ValueError:
        raise ValueError(f'invalid IPv4 address in {field}') from None


def _prefix(fields: Mapping[str, str]) -> int:
    prefix = None
    if 'subnet' in fields:
        # IPv4Network also accepts hostmasks; DHCP's subnet field must not.
        inverse = int(_address(fields['subnet'], 'subnet')) ^ _MAX_LEASE
        if inverse & (inverse + 1):
            raise ValueError('subnet must be a contiguous netmask')
        prefix = 32 - inverse.bit_length()
    if 'mask' in fields:
        numeric = _decimal(fields['mask'], 0, 32, 'mask')
        if prefix is not None and prefix != numeric:
            raise ValueError('subnet and mask disagree')
        prefix = numeric
    if prefix is None:
        raise ValueError('lease event needs subnet or mask')
    return prefix


def _unicast(address: IPv4Address, interface: IPv4Interface) -> None:
    if (type(address) is not IPv4Address or int(address) >> 24 == 0
            or address.is_loopback or address.is_multicast or address.is_reserved):
        raise ValueError('lease addresses must be unicast IPv4 addresses')
    # /31 point-to-point networks and /32 host routes have no excluded endpoints.
    network = interface.network
    if network.prefixlen < 31 and address in (network.network_address, network.broadcast_address):
        raise ValueError('lease address is the subnet network or broadcast address')


@dataclass(frozen=True, slots=True)
class Lease:
    """An immutable DHCPv4 lease; no DNS, route, or interface commands are run."""

    interface: str
    address: IPv4Interface
    routers: tuple[IPv4Address, ...]
    dns: tuple[IPv4Address, ...]
    server: IPv4Address
    lease_seconds: int

    def __post_init__(self) -> None:
        _interface(self.interface)
        if type(self.address) is not IPv4Interface:
            raise ValueError('lease address must be an IPv4Interface')
        if type(self.lease_seconds) is not int or not 1 <= self.lease_seconds <= _MAX_LEASE:
            raise ValueError('invalid lease duration')
        _unicast(self.address.ip, self.address)
        _unicast(self.server, self.address)
        for values, maximum in ((self.routers, 4), (self.dns, 6)):
            if type(values) is not tuple or len(values) > maximum:
                raise ValueError('lease address list must be a bounded tuple')
            for address in values:
                _unicast(address, self.address)

    @classmethod
    def from_event(cls, fields: Mapping[str, str], *, expected_interface: str = 'wlan0') -> 'Lease':
        """Parse whitelisted udhcpc fields, rejecting malformed or oversized data.

        ``subnet`` is a dotted contiguous netmask; ``mask`` is a decimal prefix.
        At least one must be present. Router and DNS lists may be absent or empty.
        The event name (bound/renew/deconfig) is handled by the caller.
        """
        _interface(expected_interface)
        values = _fields(fields)
        _interface(values['interface'])
        if values['interface'] != expected_interface:
            raise ValueError('unexpected lease interface')
        address = IPv4Interface((_address(values['ip'], 'ip'), _prefix(values)))
        lists = []
        for field, maximum in (('router', 4), ('dns', 6)):
            entries = values.get(field, '').split()
            if len(entries) > maximum:
                raise ValueError(f'too many {field} addresses')
            lists.append(tuple(_address(entry, field) for entry in entries))
        return cls(interface=values['interface'], address=address, routers=lists[0], dns=lists[1],
                   server=_address(values['serverid'], 'serverid'),
                   lease_seconds=_decimal(values['lease'], 1, _MAX_LEASE, 'lease'))

    def to_dict(self) -> dict:
        """Return the stable JSON-safe lease shape used in controller evidence."""
        return {'interface': self.interface, 'address': str(self.address),
                'routers': [str(address) for address in self.routers],
                'dns': [str(address) for address in self.dns], 'server': str(self.server),
                'lease_seconds': self.lease_seconds}
