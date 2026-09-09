"""The Wi-Fi deck: reading the air, and the words used to describe it.

Everything here runs on synthetic scan output, a synthetic `iw`, a temporary
configuration directory and a fake system log.  No radio is touched, no scan is
requested and no network is joined -- which is the same promise the module makes
to the desktop, so the tests are able to keep it too.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'desktop/.local/lib/oldbook'
sys.path.insert(0, str(LIB))

import wifi                                      # noqa: E402
import wifi_join                                 # noqa: E402
import wifi_hotspot                              # noqa: E402


SCAN = "\n".join((
    "bssid / frequency / signal level / flags / ssid",
    "aa:bb:cc:00:00:01\t2437\t-42\t[WPA2-PSK-CCMP][ESS]\thome-net",
    "aa:bb:cc:00:00:02\t5220\t-55\t[WPA2-PSK-CCMP][ESS]\thome-net",
    "bb:cc:dd:00:00:03\t2412\t-78\t[WPA2-EAP-CCMP][ESS]\teduroam",
    "cc:dd:ee:00:00:04\t2462\t-61\t[ESS]\tCoffee Guest",
    "dd:ee:ff:00:00:05\t5745\t-70\t[WPA2-PSK-CCMP][SAE][ESS]\tmixed",
    "ee:ff:00:00:00:06\t2437\t-88\t[WEP][ESS]\tancient",
    "ff:00:11:00:00:07\t2412\t-50\t[WPA2-PSK-CCMP][ESS]\t",
))

IW_LINK = """Connected to 02:cb:7a:19:ad:b7 (on wlan0)
\tSSID: shmecklebuckit
\tfreq: 5785.0
\tRX: 112723529 bytes (103480 packets)
\tTX: 17468496 bytes (53421 packets)
\tsignal: -54 dBm
\trx bitrate: 540.0 MBit/s
\ttx bitrate: 877.5 MBit/s
\tbss flags:\t
\tdtim period: 1
\tbeacon int: 100
"""


class Result:
    """Enough of a CompletedProcess for the callers under test."""

    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class ScanParsing(unittest.TestCase):
    def setUp(self):
        self.networks = wifi.parse_results(SCAN)
        self.by_name = {entry['ssid']: entry for entry in self.networks}

    def test_access_points_fold_into_one_network(self):
        """Two radios advertising one name are one row, not two."""
        self.assertEqual(self.by_name['home-net']['access_points'], 2)
        self.assertEqual(len(self.networks), 5)

    def test_strongest_access_point_supplies_the_detail(self):
        """The row describes the radio he would actually associate with."""
        home = self.by_name['home-net']
        self.assertEqual(home['signal'], -42)
        self.assertEqual(home['frequency'], 2437)
        self.assertEqual(home['channel'], 6)

    def test_hidden_network_is_not_offered_as_a_row(self):
        """A nameless beacon is real but cannot be clicked."""
        self.assertNotIn('', self.by_name)

    def test_networks_are_ordered_loudest_first(self):
        signals = [entry['signal'] for entry in self.networks]
        self.assertEqual(signals, sorted(signals, reverse=True))

    def test_malformed_rows_are_skipped_rather_than_raising(self):
        self.assertEqual(wifi.parse_results("header\nrubbish\n\t\t\t\t"), [])
        self.assertEqual(wifi.parse_results(""), [])
        self.assertEqual(wifi.parse_results(None), [])


class Security(unittest.TestCase):
    def test_each_flag_shape_gets_the_right_prompt(self):
        """What a menu needs to know is which question to ask next."""
        cases = {
            '[WPA2-PSK-CCMP][ESS]': ('WPA2', 'psk', False),
            '[WPA2-EAP-CCMP][ESS]': ('WPA2 Enterprise', 'eap', False),
            '[ESS]': ('Open', 'open', True),
            '[WEP][ESS]': ('WEP', 'wep', False),
            '[SAE][ESS]': ('WPA3', 'sae', False),
            '[WPA2-PSK-CCMP][SAE][ESS]': ('WPA2/3 mixed', 'psk', False),
        }
        for flags, (name, kind, is_open) in cases.items():
            with self.subTest(flags=flags):
                found = wifi.security_of(flags)
                self.assertEqual(found['name'], name)
                self.assertEqual(found['kind'], kind)
                self.assertEqual(found['open'], is_open)

    def test_enterprise_is_marked_so_the_identity_prompt_appears(self):
        self.assertTrue(wifi.security_of('[WPA2-EAP-CCMP][ESS]')['enterprise'])
        self.assertFalse(wifi.security_of('[WPA2-PSK-CCMP][ESS]')['enterprise'])


class Channels(unittest.TestCase):
    def test_all_three_bands(self):
        self.assertEqual(wifi.channel_of(2437), 6)
        self.assertEqual(wifi.channel_of(2484), 14)     # the odd one out
        self.assertEqual(wifi.channel_of(5220), 44)
        self.assertEqual(wifi.channel_of(6135), 37)
        self.assertEqual(wifi.band_of(2437), '2.4 GHz')
        self.assertEqual(wifi.band_of(5220), '5 GHz')
        self.assertEqual(wifi.band_of(6135), '6 GHz')

    def test_nonsense_frequency_claims_nothing(self):
        self.assertEqual(wifi.channel_of('grackle'), 0)
        self.assertEqual(wifi.channel_of(None), 0)
        self.assertEqual(wifi.band_of(0), '')


class Congestion(unittest.TestCase):
    def setUp(self):
        self.networks = wifi.parse_results(SCAN)

    def test_a_loud_neighbour_counts_for_more_than_a_distant_one(self):
        loads = {entry['channel']: entry['weight'] for entry in wifi.congestion(self.networks)}
        self.assertGreater(loads[6], loads[1])

    def test_only_non_overlapping_channels_are_offered(self):
        self.assertIn(wifi.quietest_channel(self.networks, '2.4'), (1, 6, 11))
        self.assertIn(wifi.quietest_channel(self.networks, '5'),
                      (36, 40, 44, 48, 149, 153, 157, 161))

    def test_the_busiest_channel_is_not_the_one_chosen(self):
        """Channel 6 carries the loudest network in the sample, so it loses."""
        self.assertNotEqual(wifi.quietest_channel(self.networks, '2.4'), 6)

    def test_an_empty_sky_still_yields_a_usable_channel(self):
        """With nothing heard every candidate ties, and any of them is correct."""
        self.assertIn(wifi.quietest_channel([], '2.4'), (1, 6, 11))
        self.assertIn(wifi.quietest_channel([], '5'),
                      (36, 40, 44, 48, 149, 153, 157, 161))


class Drawing(unittest.TestCase):
    def test_the_ramp_climbs_with_the_signal(self):
        steps = [wifi.quality(d)[0] for d in (-95, -80, -70, -60, -45)]
        self.assertEqual(steps, [0, 1, 2, 3, 4])

    def test_locked_and_open_networks_are_never_the_same_glyph(self):
        """The open one is the dangerous one; it must not look identical."""
        for dbm in (-45, -60, -70, -80, -95):
            with self.subTest(dbm=dbm):
                self.assertNotEqual(wifi.bars(dbm), wifi.bars(dbm, locked=True))

    def test_a_steady_signal_reads_as_steady_not_as_noise(self):
        """A healthy link wobbles a few dBm; that must not draw a mountain range."""
        self.assertEqual(len(set(wifi.sparkline([-60, -60, -60, -60]))), 1)
        self.assertLessEqual(len(set(wifi.sparkline([-54, -57, -55, -56, -54]))), 2)

    def test_a_falling_signal_draws_a_descending_line(self):
        drawn = wifi.sparkline([-45, -60, -75, -88])
        heights = [wifi.BLOCKS.index(character) for character in drawn]
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertGreater(heights[0], heights[-1])

    def test_the_scale_is_absolute_so_two_links_can_be_compared(self):
        """The same reading draws the same height whatever else is in the run."""
        self.assertEqual(wifi.sparkline([-50, -50])[0], wifi.sparkline([-50, -85])[0])

    def test_readings_beyond_the_scale_are_clamped_rather_than_overflowing(self):
        drawn = wifi.sparkline([-10, -120])
        self.assertEqual(drawn[0], wifi.BLOCKS[-1])
        self.assertEqual(drawn[-1], wifi.BLOCKS[0])

    def test_too_few_readings_draw_nothing(self):
        self.assertEqual(wifi.sparkline([]), '')
        self.assertEqual(wifi.sparkline([-60]), '')

    def test_every_glyph_is_outside_the_ascii_range(self):
        """The house style is Unicode; plain ASCII is the degraded path only."""
        for glyph in wifi.BARS + wifi.LOCKED_BARS + (wifi.OFFLINE_GLYPH,):
            self.assertGreater(ord(glyph), 0x1000)


class LiveLink(unittest.TestCase):
    def test_iw_output_becomes_a_record(self):
        with patch.object(wifi.subprocess, 'run', return_value=Result(IW_LINK)):
            record = wifi.link('wlan0')
        self.assertEqual(record['ssid'], 'shmecklebuckit')
        self.assertEqual(record['bssid'], '02:cb:7a:19:ad:b7')
        self.assertEqual(record['signal'], -54)
        self.assertEqual(record['frequency'], 5785)
        self.assertEqual(record['channel'], 157)
        self.assertEqual(record['band'], '5 GHz')
        self.assertEqual(record['rx_bitrate'], 540.0)
        self.assertEqual(record['tx_bitrate'], 877.5)

    def test_not_connected_is_an_empty_record_rather_than_a_guess(self):
        with patch.object(wifi.subprocess, 'run', return_value=Result('Not connected.\n')):
            self.assertEqual(wifi.link('wlan0'), {})

    def test_a_missing_iw_does_not_take_the_panel_down(self):
        with patch.object(wifi.subprocess, 'run', side_effect=OSError('no iw')):
            self.assertEqual(wifi.link('wlan0'), {})


class Failures(unittest.TestCase):
    def test_a_refusal_carries_the_tool_s_own_words(self):
        """A message that drops the reason has thrown away the useful part."""
        error = wifi.WifiError('The supplicant refused it.', 'WRONG_KEY')
        self.assertIn('WRONG_KEY', error.told())

    def test_a_missing_control_socket_says_how_to_fix_it(self):
        with patch.object(wifi, 'socket_ready', return_value=False):
            with self.assertRaises(wifi.WifiError) as caught:
                wifi.wpa('status', iface='wlan0')
        self.assertIn('ctrl_interface', caught.exception.cause)

    def test_the_log_supplies_the_reason_the_supplicant_will_not(self):
        with tempfile.TemporaryDirectory() as folder:
            messages = Path(folder) / 'messages'
            messages.write_text(
                'Sep  9 10:00:00 catbed wpa_supplicant[123]: wlan0: WPA: '
                '4-Way Handshake failed - pre-shared key may be incorrect\n')
            with patch.object(wifi_join, 'MESSAGES', messages):
                self.assertEqual(wifi_join.log_reason(), 'The password was not accepted.')

    def test_an_unreadable_log_simply_says_nothing(self):
        with patch.object(wifi_join, 'MESSAGES', Path('/nonexistent/messages')):
            self.assertEqual(wifi_join.log_reason(), '')


class Preferences(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.environ = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.folder.name})
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.addCleanup(self.folder.cleanup)

    def test_an_unwritten_file_yields_the_quiet_defaults(self):
        preference = wifi.preferences()
        self.assertEqual(preference['default_trust'], 'public')
        self.assertFalse(preference['sound'])

    def test_a_stored_map_merges_rather_than_replaces(self):
        """Setting one shield must not delete the other two."""
        wifi.save_preferences({'shields': {'public': {'mac': 'permanent'}}})
        shields = wifi.preferences()['shields']
        self.assertEqual(shields['public']['mac'], 'permanent')
        self.assertIn('home', shields)

    def test_the_file_is_not_world_readable(self):
        wifi.save_preferences({'networks': {}})
        self.assertEqual(os.stat(wifi.config_path()).st_mode & 0o077, 0)

    def test_an_unknown_network_is_held_at_the_careful_posture(self):
        self.assertEqual(wifi.trust_of('some cafe'), 'public')

    def test_remembering_one_network_leaves_the_others_alone(self):
        wifi.remember('home-net', trust='home')
        wifi.remember('cafe', trust='public')
        self.assertEqual(wifi.trust_of('home-net'), 'home')
        self.assertEqual(wifi.trust_of('cafe'), 'public')

    def test_a_corrupt_file_falls_back_instead_of_raising(self):
        wifi.config_path().parent.mkdir(parents=True, exist_ok=True)
        wifi.config_path().write_text('{ not json')
        self.assertEqual(wifi.preferences()['default_trust'], 'public')


class Logbook(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'logbook.json'
        self.patched = patch.object(wifi_join, 'LOGBOOK', self.path)
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.addCleanup(self.folder.cleanup)

    def test_arrivals_accumulate(self):
        wifi_join.record_arrival('home-net', '10.0.0.5', 'aa:bb')
        entry = wifi_join.record_arrival('home-net', '10.0.0.5', 'aa:bb')
        self.assertEqual(entry['joins'], 2)
        self.assertEqual(entry['last_address'], '10.0.0.5')

    def test_the_first_arrival_is_kept_apart_from_the_latest(self):
        first = wifi_join.record_arrival('home-net')
        time.sleep(0.01)
        later = wifi_join.record_arrival('home-net')
        self.assertEqual(first['first_seen'], later['first_seen'])
        self.assertGreaterEqual(later['last_seen'], first['last_seen'])

    def test_ages_are_rounded_to_something_worth_reading(self):
        now = time.time()
        self.assertEqual(wifi_join.since(now - 86400 * 23), '3 weeks ago')
        self.assertEqual(wifi_join.since(now - 3600 * 2), '2 hours ago')
        self.assertEqual(wifi_join.since(now - 86400), '1 day ago')
        self.assertEqual(wifi_join.since(now - 5), 'just now')
        self.assertEqual(wifi_join.since(None), '')


class ConfigGrammar(unittest.TestCase):
    def test_a_network_name_cannot_break_out_of_its_quotes(self):
        """Names come off the air; the supplicant's grammar must survive them."""
        self.assertEqual(wifi_join.quote('plain'), '"plain"')
        self.assertEqual(wifi_join.quote('say "hi"'), '"say \\"hi\\""')
        self.assertEqual(wifi_join.quote('back\\slash'), '"back\\\\slash"')

    def test_a_shell_shaped_name_is_still_only_a_name(self):
        quoted = wifi_join.quote('; rm -rf ~')
        self.assertTrue(quoted.startswith('"') and quoted.endswith('"'))


class Hotspot(unittest.TestCase):
    def test_the_access_point_follows_the_uplink_channel(self):
        """One channel is a hardware limit, not a preference to be overridden."""
        preference = {'hotspot': {'channel': 11, 'band': '2.4'}}
        with patch.object(wifi_hotspot, 'uplink_channel', return_value=157):
            channel, why = wifi_hotspot.choose_channel(preference, [], 'wlan0')
        self.assertEqual(channel, 157)
        self.assertIn('cannot host', why)

    def test_offline_the_configured_channel_is_honoured(self):
        preference = {'hotspot': {'channel': 11, 'band': '2.4'}}
        with patch.object(wifi_hotspot, 'uplink_channel', return_value=0):
            channel, _why = wifi_hotspot.choose_channel(preference, [], 'wlan0')
        self.assertEqual(channel, 11)

    def test_offline_and_automatic_picks_the_quietest(self):
        preference = {'hotspot': {'channel': 'auto', 'band': '2.4'}}
        with patch.object(wifi_hotspot, 'uplink_channel', return_value=0):
            channel, why = wifi_hotspot.choose_channel(
                preference, wifi.parse_results(SCAN), 'wlan0')
        self.assertIn(channel, (1, 6, 11))
        self.assertIn('quietest', why)

    def test_the_band_follows_the_channel_number(self):
        self.assertIn('hw_mode=g', wifi_hotspot.hostapd_config('x', 6, 'password12'))
        self.assertIn('hw_mode=a', wifi_hotspot.hostapd_config('x', 157, 'password12'))

    def test_clients_cannot_reach_each_other(self):
        self.assertIn('ap_isolate=1', wifi_hotspot.hostapd_config('x', 6, 'password12'))

    def test_the_firewall_rules_live_in_their_own_table(self):
        """Flushing the ruleset wholesale would take OpenSnitch down with it."""
        ruleset = wifi_hotspot.nft_ruleset('wlan0')
        self.assertIn(f'table inet {wifi_hotspot.NFT_TABLE}', ruleset)
        self.assertNotIn('flush ruleset', ruleset)

    def test_dns_and_dhcp_are_never_served_onto_the_uplink(self):
        config = wifi_hotspot.dnsmasq_config()
        self.assertIn(f'interface={wifi_hotspot.AP_IFACE}', config)
        self.assertIn('bind-interfaces', config)

    def test_the_missing_packages_are_named_rather_than_guessed_at(self):
        with patch.object(wifi_hotspot.shutil, 'which', return_value=None):
            self.assertEqual(wifi_hotspot.missing_tools(), ['hostapd', 'dnsmasq'])
        with patch.object(wifi_hotspot.shutil, 'which', return_value='/usr/sbin/x'):
            self.assertEqual(wifi_hotspot.missing_tools(), [])


class Exporting(unittest.TestCase):
    def test_passwords_are_never_written_to_the_exported_list(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'networks.json'
            with patch.object(wifi, 'saved', return_value=[
                    {'ssid': 'home-net', 'id': 0, 'bssid': 'any',
                     'current': True, 'disabled': False}]):
                count = wifi_join.export_saved(destination)
            document = json.loads(destination.read_text())
            self.assertEqual(count, 1)
            self.assertFalse(document['secrets'])
            self.assertNotIn('psk', destination.read_text())
            self.assertEqual(os.stat(destination).st_mode & 0o077, 0)


class Importing(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.environ = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.folder.name})
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.addCleanup(self.folder.cleanup)

    def test_an_export_restores_postures_on_the_other_laptop(self):
        source = Path(self.folder.name) / 'networks.json'
        source.write_text(json.dumps({'networks': [
            {'ssid': 'home-net', 'trust': 'home'},
            {'ssid': 'cafe', 'trust': 'public'},
        ], 'secrets': False}))
        with patch.object(wifi, 'saved', return_value=[]):
            restored, pending = wifi_join.import_saved(source)
        self.assertEqual(restored, 2)
        self.assertEqual(wifi.trust_of('home-net'), 'home')

    def test_networks_without_a_password_here_are_counted_and_named(self):
        """An import cannot carry secrets, so it must say what is still needed."""
        source = Path(self.folder.name) / 'networks.json'
        source.write_text(json.dumps({'networks': [{'ssid': 'cafe', 'trust': 'public'}]}))
        with patch.object(wifi, 'saved', return_value=[]):
            _restored, pending = wifi_join.import_saved(source)
        self.assertEqual(pending, 1)

    def test_a_network_already_saved_here_is_not_counted_as_pending(self):
        source = Path(self.folder.name) / 'networks.json'
        source.write_text(json.dumps({'networks': [{'ssid': 'home-net', 'trust': 'home'}]}))
        with patch.object(wifi, 'saved', return_value=[
                {'ssid': 'home-net', 'id': 0, 'bssid': 'any',
                 'current': True, 'disabled': False}]):
            _restored, pending = wifi_join.import_saved(source)
        self.assertEqual(pending, 0)

    def test_a_nameless_entry_is_skipped_rather_than_stored(self):
        source = Path(self.folder.name) / 'networks.json'
        source.write_text(json.dumps({'networks': [{'trust': 'home'}, {}]}))
        with patch.object(wifi, 'saved', return_value=[]):
            restored, _pending = wifi_join.import_saved(source)
        self.assertEqual(restored, 0)


class Priority(unittest.TestCase):
    def test_preferring_one_network_leaves_the_rest_of_the_order_alone(self):
        """'Prefer this' is one number above the top, not a reshuffle."""
        calls = []

        def fake(*arguments, **kwargs):
            calls.append(arguments)
            return 'OK'

        with patch.object(wifi_join, 'priorities', return_value={0: 3, 1: 7, 2: 1}), \
             patch.object(wifi, 'wpa', side_effect=fake):
            value = wifi_join.promote(2)
        self.assertEqual(value, 8)
        self.assertIn(('set_network', 2, 'priority', '8'), calls)

    def test_an_empty_list_starts_the_order_rather_than_failing(self):
        with patch.object(wifi_join, 'priorities', return_value={}), \
             patch.object(wifi, 'wpa', return_value='OK'):
            self.assertEqual(wifi_join.promote(0), 1)


if __name__ == '__main__':
    unittest.main()
