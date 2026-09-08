"""Pure DHCP lease validation; no interfaces, routes or services are changed."""
from dataclasses import FrozenInstanceError
from ipaddress import IPv4Address, IPv4Interface
import json
from pathlib import Path
import sys
import tempfile
import unittest


LIBRARY = Path(__file__).parents[1] / 'root/usr/local/lib'
sys.path.insert(0, str(LIBRARY))
from privacyctl_runtime.lease import Lease


class LeaseTests(unittest.TestCase):
    def event(self, **changes):
        values = {'interface': 'wlan0', 'ip': '192.0.2.17', 'subnet': '255.255.255.0',
                  'mask': '24', 'router': '192.0.2.1', 'dns': '192.0.2.53 198.51.100.53',
                  'lease': '3600', 'serverid': '192.0.2.2'}
        values.update(changes)
        return values

    def test_valid_lease_has_typed_immutable_fields_and_json_safe_form(self):
        lease = Lease.from_event(self.event())
        self.assertEqual(lease.interface, 'wlan0')
        self.assertEqual(lease.address, IPv4Interface('192.0.2.17/24'))
        self.assertEqual(lease.routers, (IPv4Address('192.0.2.1'),))
        self.assertEqual(lease.dns, (IPv4Address('192.0.2.53'), IPv4Address('198.51.100.53')))
        self.assertEqual(lease.server, IPv4Address('192.0.2.2'))
        self.assertEqual(lease.lease_seconds, 3600)
        self.assertEqual(json.loads(json.dumps(lease.to_dict())), {
            'interface': 'wlan0', 'address': '192.0.2.17/24', 'routers': ['192.0.2.1'],
            'dns': ['192.0.2.53', '198.51.100.53'], 'server': '192.0.2.2', 'lease_seconds': 3600})
        with self.assertRaises(FrozenInstanceError):
            lease.lease_seconds = 12

    def test_shell_tokens_and_controls_are_rejected_without_execution(self):
        with tempfile.TemporaryDirectory() as work:
            marker = Path(work) / 'must-not-exist'
            for field in ('ip', 'subnet', 'mask', 'router', 'dns', 'lease', 'serverid'):
                for value in (f'$(touch {marker})', f'`touch {marker}`', '192.0.2.1;echo injected',
                              '192.0.2.1\n192.0.2.2', '192.0.2.1\x00', '192.0.2.1\t192.0.2.2'):
                    with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                        Lease.from_event(self.event(**{field: value}))
            self.assertFalse(marker.exists())

    def test_noncontiguous_hostmask_and_disagreeing_masks_are_rejected(self):
        for subnet in ('255.0.255.0', '255.255.0.255', '0.0.0.255', '24', '255.255.255.256'):
            with self.subTest(subnet=subnet), self.assertRaises(ValueError):
                Lease.from_event(self.event(subnet=subnet))
        for mask in ('-1', '33', '255.255.255.0', '24.0', '+24', '23'):
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                Lease.from_event(self.event(mask=mask))

    def test_either_mask_form_alone_and_all_contiguous_masks_are_supported(self):
        for prefix in range(33):
            address = IPv4Interface(f'192.0.2.17/{prefix}')
            values = self.event(subnet=str(address.netmask), mask=str(prefix))
            for absent in ('mask', 'subnet'):
                single = dict(values)
                del single[absent]
                with self.subTest(prefix=prefix, absent=absent):
                    self.assertEqual(Lease.from_event(single).address.network.prefixlen, prefix)

    def test_assigned_network_and_broadcast_addresses_are_not_hosts(self):
        for address in ('192.0.2.0', '192.0.2.255'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                Lease.from_event(self.event(ip=address))

    def test_slash31_both_endpoints_and_slash32_host_are_explicitly_valid(self):
        for prefix, subnet in ((31, '255.255.255.254'), (32, '255.255.255.255')):
            for address in ('192.0.2.0', '192.0.2.1'):
                with self.subTest(prefix=prefix, address=address):
                    result = Lease.from_event(self.event(ip=address, mask=str(prefix), subnet=subnet))
                    self.assertEqual(str(result.address), f'{address}/{prefix}')

    def test_expected_interface_is_exact_and_can_be_private_test_interface(self):
        with self.assertRaises(ValueError):
            Lease.from_event(self.event(interface='lease-test0'))
        self.assertEqual(Lease.from_event(self.event(interface='lease-test0'),
                                         expected_interface='lease-test0').interface, 'lease-test0')
        for interface in ('', '-wlan0', 'wlan0;id', 'wlan0\n', '../wlan0', 'wlan0:1', 'x' * 16):
            with self.subTest(interface=interface), self.assertRaises(ValueError):
                Lease.from_event(self.event(interface=interface), expected_interface=interface)

    def test_all_address_roles_reject_non_unicast_and_ambiguous_notation(self):
        for field in ('ip', 'router', 'dns', 'serverid'):
            for value in ('0.0.0.0', '0.1.2.3', '127.0.0.1', '224.0.0.1', '239.1.2.3',
                          '240.0.0.1', '255.255.255.255', '192.0.2.255', '192.0.2.0',
                          '192.0.02.1', '3232235777', '192.0.2.1/24', '2001:db8::1'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    Lease.from_event(self.event(**{field: value}))

    def test_private_link_local_documentation_and_remote_unicast_are_data_not_trust(self):
        for server in ('10.0.0.1', '169.254.1.1', '198.51.100.1', '8.8.8.8'):
            with self.subTest(server=server):
                result = Lease.from_event(self.event(serverid=server, router=server, dns=server))
                self.assertEqual(result.server, IPv4Address(server))

    def test_router_and_dns_limits_preserve_order_without_excess_entries(self):
        router = ' '.join(f'192.0.2.{i}' for i in range(1, 5))
        dns = ' '.join(f'198.51.100.{i}' for i in range(1, 7))
        result = Lease.from_event(self.event(router=router, dns=dns))
        self.assertEqual(tuple(map(str, result.routers)), tuple(router.split()))
        self.assertEqual(tuple(map(str, result.dns)), tuple(dns.split()))
        for field, value in (('router', router + ' 192.0.2.5'), ('dns', dns + ' 198.51.100.7')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                Lease.from_event(self.event(**{field: value}))
        result = Lease.from_event(self.event(router='', dns=''))
        self.assertEqual((result.routers, result.dns), ((), ()))
        values = self.event()
        del values['router'], values['dns']
        self.assertEqual(Lease.from_event(values).routers, ())

    def test_lease_time_is_unsigned_nonzero_bounded_decimal(self):
        for value in ('0', '-1', '+1', '1.0', '1e3', '4294967296', '', 'inf', '１２'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Lease.from_event(self.event(lease=value))
        for value in ('1', '4294967295'):
            self.assertEqual(Lease.from_event(self.event(lease=value)).lease_seconds, int(value))

    def test_required_fields_types_and_unknown_keys_are_rejected(self):
        for absent in ('interface', 'ip', 'lease', 'serverid'):
            values = self.event()
            del values[absent]
            with self.subTest(absent=absent), self.assertRaises(ValueError):
                Lease.from_event(values)
        values = self.event()
        del values['subnet'], values['mask']
        with self.assertRaises(ValueError):
            Lease.from_event(values)
        for values in (self.event(action='deconfig'), self.event(lease=3600),
                       self.event(ip=None), self.event(dns=['8.8.8.8']), [], None):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Lease.from_event(values)

    def test_field_and_aggregate_payload_bounds_precede_parsing(self):
        with self.assertRaisesRegex(ValueError, 'field.*large'):
            Lease.from_event(self.event(dns=' ' * 257))
        with self.assertRaisesRegex(ValueError, 'payload.*large'):
            Lease.from_event({key: ' ' * 128 for key in self.event()})

    def test_direct_construction_cannot_bypass_value_invariants(self):
        valid = Lease.from_event(self.event())
        values = {name: getattr(valid, name) for name in
                  ('interface', 'address', 'routers', 'dns', 'server', 'lease_seconds')}
        for key, bad in (('lease_seconds', True), ('lease_seconds', 0),
                         ('address', IPv4Interface('192.0.2.255/24')),
                         ('routers', (IPv4Address('224.0.0.1'),)), ('dns', ['192.0.2.1']),
                         ('server', IPv4Address('0.0.0.0'))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Lease(**dict(values, **{key: bad}))


if __name__ == '__main__':
    unittest.main()
