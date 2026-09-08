"""Read the real private allowlist parser without accessing host networking."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / 'root/usr/local/sbin/privacyctl'
loader = importlib.machinery.SourceFileLoader('privacyctl_profiles', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
privacyctl = importlib.util.module_from_spec(spec)
loader.exec_module(privacyctl)


@unittest.skipUnless(os.geteuid() == 0, 'private policy ownership requires root')
class ProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'profiles'

    def policy(self, content):
        self.path.write_text(content)
        self.path.chmod(0o600)

    def test_exact_configured_home_ssid_is_independent_of_command_label(self):
        self.policy('profile|shmecklebucket|7|My exact home SSID\n')
        self.assertEqual(privacyctl.read_profile('shmecklebucket', self.path),
                         (7, 'My exact home SSID'))

    def test_selected_profile_keeps_exact_case_and_spaces(self):
        self.policy('# private policy\nprofile|iphone-hotspot|12|Jack’s iPhone \n')
        self.assertEqual(privacyctl.read_profile('iphone-hotspot', self.path),
                         (12, 'Jack’s iPhone '))

    def test_missing_or_duplicate_selected_profile_refuses(self):
        for content in ('# no trusted profiles yet\n',
                        'profile|iphone-hotspot|1|Phone\nprofile|iphone-hotspot|2|Phone\n'):
            with self.subTest(content=content):
                self.policy(content)
                with self.assertRaises(privacyctl.PrivacyError):
                    privacyctl.read_profile('iphone-hotspot', self.path)

    def test_malformed_policy_is_not_partially_accepted(self):
        for bad in ('profile|iphone-hotspot|１２|Phone',
                    'profile|iphone-hotspot|-1|Phone',
                    'profile|iphone-hotspot|2147483648|Phone',
                    'profile|unknown|2|Phone',
                    'profile|iphone-hotspot|2|',
                    'profile|iphone-hotspot|2|Phone|extra',
                    'profile|iphone-hotspot|2|Phone\x00',
                    'profile|iphone-hotspot|2|' + 'é' * 17):
            with self.subTest(bad=bad):
                self.policy('profile|shmecklebucket|0|shmecklebucket\n' + bad + '\n')
                with self.assertRaises(privacyctl.PrivacyError):
                    privacyctl.read_profile('shmecklebucket', self.path)

    def test_symlink_private_mode_and_owner_are_enforced(self):
        self.policy('profile|shmecklebucket|0|shmecklebucket\n')
        link = self.path.with_name('link')
        link.symlink_to(self.path)
        with self.assertRaises(privacyctl.PrivacyError):
            privacyctl.read_profile('shmecklebucket', link)
        self.path.chmod(0o644)
        with self.assertRaises(privacyctl.PrivacyError):
            privacyctl.read_profile('shmecklebucket', self.path)
        self.path.chmod(0o600)
        os.chown(self.path, 1000, 1000)
        with self.assertRaises(privacyctl.PrivacyError):
            privacyctl.read_profile('shmecklebucket', self.path)

    def test_oversized_and_non_utf8_policy_refuse(self):
        for content in (b'#' + b'x' * 8192, b'\xff'):
            self.path.write_bytes(content)
            self.path.chmod(0o600)
            with self.assertRaises(privacyctl.PrivacyError):
                privacyctl.read_profile('shmecklebucket', self.path)


if __name__ == '__main__':
    unittest.main()
