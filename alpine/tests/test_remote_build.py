"""Packages build on a build host; only the signature is applied here."""
import contextlib
import gzip
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader(
    'remote_build', str(Path(__file__).parents[1] / 'bin/remote-build'))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

CACHE = Path.home() / '.cache/oldbook-apks'


def gzip_tar(members):
    plain = io.BytesIO()
    with tarfile.open(fileobj=plain, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for name, payload in members.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(payload)
            entry.mtime = 0
            archive.addfile(entry, io.BytesIO(payload))
    body = plain.getvalue()
    while body.endswith(b'\0' * tarfile.BLOCKSIZE):
        body = body[:-tarfile.BLOCKSIZE]
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as stream:
        stream.write(body)
    return compressed.getvalue()


class SignatureTest(unittest.TestCase):
    """An APK v2 signature covers the control segment and nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='remote-build-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.key = cls.base / 'builder.rsa'
        subprocess.run(['openssl', 'genrsa', '-out', str(cls.key), '2048'],
                       check=True, capture_output=True)
        subprocess.run(['openssl', 'rsa', '-in', str(cls.key), '-pubout',
                        '-out', str(cls.key) + '.pub'], check=True, capture_output=True)

    def unsigned(self, name='fixture-1-r0.apk'):
        path = self.base / name
        path.write_bytes(gzip_tar({'.PKGINFO': b'pkgname = fixture\n'}) +
                         gzip_tar({'usr/share/fixture': b'payload'}))
        return path

    def test_an_unsigned_package_has_two_segments_and_a_signed_one_has_three(self):
        path = self.unsigned()
        signature, control, data = m.apk_parts(path.read_bytes())
        self.assertEqual(signature, b'')
        m.sign(path, self.key, 'builder.rsa.pub')
        again = m.apk_parts(path.read_bytes())
        self.assertNotEqual(again[0], b'')
        self.assertEqual(again[1:], (control, data))

    def test_the_signature_covers_the_control_segment_alone(self):
        path = self.unsigned()
        _, control, data = m.apk_parts(path.read_bytes())
        m.sign(path, self.key, 'builder.rsa.pub')
        segment = m.apk_parts(path.read_bytes())[0]
        archive = tarfile.open(fileobj=io.BytesIO(gzip.decompress(segment)))
        member = archive.getmembers()[0]
        self.assertEqual(member.name, '.SIGN.RSA.builder.rsa.pub')
        for candidate, expected in ((control, 0), (control + data, 1), (data, 1)):
            signed = self.base / 'signed.bin'
            signed.write_bytes(candidate)
            (self.base / 'sig.bin').write_bytes(archive.extractfile(member).read())
            result = subprocess.run(
                ['openssl', 'dgst', '-sha1', '-verify', str(self.key) + '.pub',
                 '-signature', str(self.base / 'sig.bin'), str(signed)],
                capture_output=True)
            self.assertEqual(result.returncode, expected)

    def test_the_signature_segment_leaves_the_tar_stream_open(self):
        # An end-of-archive marker here hides the control and data segments
        # behind it and apk rejects the whole file as inconsistent.
        segment = m.signature_segment(b'x' * 512, 'builder.rsa.pub')
        self.assertFalse(gzip.decompress(segment).endswith(b'\0' * (2 * tarfile.BLOCKSIZE)))

    def test_signing_the_same_package_twice_produces_the_same_bytes(self):
        first, second = self.unsigned('a.apk'), self.unsigned('b.apk')
        m.sign(first, self.key, 'builder.rsa.pub')
        m.sign(second, self.key, 'builder.rsa.pub')
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_resigning_replaces_the_previous_signature_rather_than_stacking_one(self):
        path = self.unsigned()
        m.sign(path, self.key, 'builder.rsa.pub')
        once = path.read_bytes()
        m.sign(path, self.key, 'builder.rsa.pub')
        self.assertEqual(path.read_bytes(), once)
        self.assertEqual(len(m.gzip_segments(path.read_bytes())), 3)

    def test_a_truncated_archive_is_refused(self):
        path = self.unsigned()
        with self.assertRaises(RuntimeError):
            m.apk_parts(path.read_bytes()[:-40])


@unittest.skipUnless(shutil.which('apk') and CACHE.is_dir(),
                     'native identity checks need apk and the archive cache')
class NativeIdentityTest(unittest.TestCase):
    """Re-signing a real package must not change what package it is."""

    @classmethod
    def setUpClass(cls):
        cls.sample = next(iter(sorted(CACHE.glob('*.apk'), key=lambda p: p.stat().st_size)), None)
        if cls.sample is None:
            raise unittest.SkipTest('no archived APK to re-sign')
        try:
            cls.key_name = m.public_key_name(m.PRIVATE_KEY)
        except RuntimeError as error:
            raise unittest.SkipTest(str(error))
        if not m.PRIVATE_KEY.is_file():
            raise unittest.SkipTest('no local signing key')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='remote-build-native-')
        self.addCleanup(self.temporary.cleanup)
        self.copy = Path(self.temporary.name) / self.sample.name
        shutil.copyfile(self.sample, self.copy)

    def test_the_package_identity_survives_a_new_signature(self):
        before = m.identity(self.copy)
        m.sign(self.copy)
        self.assertEqual(m.identity(self.copy), before)

    def test_apk_accepts_a_package_this_machine_signed(self):
        m.sign(self.copy)
        subprocess.run(['apk', 'verify', str(self.copy)], check=True, capture_output=True)


class PolicyTest(unittest.TestCase):
    """This machine is the desktop; it refuses to be the build machine."""

    def test_building_here_is_refused_and_names_the_escape_hatch(self):
        with self.assertRaises(RuntimeError) as caught:
            m.build(['waybar'], force_local=True)
        self.assertIn(m.ESCAPE, str(caught.exception))

    def test_the_guard_shim_defers_to_the_escape_hatch(self):
        self.assertIn(f'${{{m.ESCAPE}:-}}', m.GUARD_SHIM)
        self.assertIn('exec /usr/bin/abuild "$@"', m.GUARD_SHIM)
        self.assertIn('remote-build build', m.GUARD_SHIM)

    def test_an_unknown_package_is_named_before_any_host_is_contacted(self):
        with patch.object(m, 'select_host', side_effect=AssertionError('contacted a host')):
            with self.assertRaises(RuntimeError) as caught:
                m.build(['not-a-package'])
        self.assertIn('not-a-package', str(caught.exception))

    def test_every_refused_host_is_reported_rather_than_only_the_last(self):
        with patch.object(m, 'reachable', return_value=(False, ['policy says no'])):
            with self.assertRaises(RuntimeError) as caught:
                m.select_host()
        for host in m.HOSTS:
            self.assertIn(host, str(caught.exception))

    def test_planning_a_build_contacts_nothing(self):
        with patch.object(m.subprocess, 'run', side_effect=AssertionError('ran a command')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.build(['waybar'], host='alienware', plan=True), [])


class CheckoutTest(unittest.TestCase):
    """The tool reads its work from this checkout, not from installed state."""

    def test_every_package_directory_with_an_apkbuild_is_buildable(self):
        names = m.buildable()
        self.assertIn('waybar', names)
        self.assertEqual(names, sorted(names))
        for name in names:
            self.assertTrue((m.PACKAGES / name / 'APKBUILD').is_file())

    def test_versions_come_from_the_apkbuild(self):
        package, version = m.describe('waybar')
        self.assertEqual(package, 'waybar')
        self.assertRegex(version, r'^\d[\w.]*-r\d+$')

    @unittest.skipUnless(shutil.which('sh'), 'needs a shell')
    def test_the_remote_script_is_valid_shell(self):
        subprocess.run(['sh', '-n'], input=m.REMOTE_SCRIPT.encode(),
                       check=True, capture_output=True)

    def test_the_remote_script_generates_its_own_throwaway_signing_key(self):
        # The private key stays on this machine. The far side signs with a key
        # it invents and we replace that signature on the way back. The script
        # does name .rsa paths, because it has to find the key abuild-keygen
        # just made and install the public half itself, so what is asserted is
        # that every key path it touches belongs to the container: this
        # machine's key is never named, and no key is ever sent in.
        self.assertIn('abuild-keygen', m.REMOTE_SCRIPT)
        self.assertNotIn(str(m.PRIVATE_KEY), m.REMOTE_SCRIPT)
        self.assertNotIn(str(m.PRIVATE_KEY.parent), m.REMOTE_SCRIPT)
        self.assertNotIn(str(Path.home()), m.REMOTE_SCRIPT)
        for line in m.REMOTE_SCRIPT.splitlines():
            if '.rsa' in line and not line.lstrip().startswith('#'):
                with self.subTest(line=line.strip()):
                    self.assertTrue(
                        '$keys' in line or '$mine' in line or '$candidate' in line,
                        'a key path outside the container appears in the remote script')


if __name__ == '__main__':
    unittest.main()
