import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/'home/.local/bin/spaceghost-wifi'
spec = importlib.util.spec_from_loader('wifi_menu', SourceFileLoader('wifi_menu', str(path)))
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class WifiMenuTests(unittest.TestCase):
    def test_hidden_networks_and_duplicate_radios_do_not_clutter_picker(self):
        scan = 'bssid / frequency / signal level / flags / ssid\na\t2412\t-50\t[WPA2-PSK-CCMP][ESS]\tCafe\nb\t5200\t-60\t[WPA2-PSK-CCMP][ESS]\tCafe\nc\t2412\t-30\t[ESS]\t\n'
        saved = 'network id / ssid / bssid / flags\n6\tCafe\tany\t\n7\tCafe\tany\t[CURRENT]\n8\tOffline\tany\t\n'
        result = menu.networks(scan, saved)
        self.assertEqual([x['ssid'] for x in result], [b'Cafe', b'Offline'])
        self.assertEqual(result[0]['ids'], [6, 7])
        self.assertEqual(result[0]['current'], 7)
        self.assertEqual(result[0]['signal'], -50)
        self.assertIn(5200, result[0]['frequencies'])

    def test_escaped_ssid_remains_exact_but_cannot_add_menu_rows(self):
        raw = menu.ssid_bytes(r'Cafe\x20A\nB')
        self.assertEqual(raw, b'Cafe A\nB')
        self.assertNotIn('\n', menu.display_ssid(raw))

    def test_wpa_key_derivation_matches_published_vector(self):
        self.assertEqual(menu.psk('password', b'IEEE'), 'f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e')
        with self.assertRaises(ValueError):
            menu.psk('short', b'IEEE')

    def test_failed_join_removes_temporary_profile_and_returns_to_previous(self):
        class Radio:
            def __init__(self):
                self.current = '7'
                self.profiles = {'7', '9'}
            def command(self, command, *args, **kwargs):
                if command == 'status':
                    return 'id='+self.current+'\nwpa_state=COMPLETED'
                if command == 'select_network':
                    self.current = str(args[0])
                if command == 'remove_network':
                    self.profiles.discard(str(args[0]))
                return 'OK'
        radio = Radio()
        result = menu.activate(radio, 9, [7], created=True, timeout=0)
        self.assertFalse(result)
        self.assertEqual(radio.current, '7')
        self.assertEqual(radio.profiles, {'7'})


if __name__ == '__main__':
    unittest.main()
