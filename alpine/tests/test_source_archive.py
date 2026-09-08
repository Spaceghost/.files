import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('source_archive', str(REPO / 'alpine/bin/source-archive'))
spec = importlib.util.spec_from_loader(loader.name, loader)
archive = importlib.util.module_from_spec(spec)
loader.exec_module(archive)


class SourceArchiveTests(unittest.TestCase):
    def entry(self, content=b'expected source archive'):
        digest = hashlib.sha256(content).hexdigest()
        return {'name': 'source.tar.gz', 'sha256': digest,
                'kind': 'opensnitch', 'artifact': f'sha256/{digest}/source.tar.gz'}

    def test_corrupt_cache_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            path = cache / 'source.tar.gz'
            path.write_bytes(b'corrupt evidence')
            with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                archive.export([self.entry()], cache)
            self.assertEqual(path.read_bytes(), b'corrupt evidence')

    def test_symlink_cache_and_symlink_artifacts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / 'real'
            real.mkdir()
            link = base / 'link'
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                archive.export([self.entry()], link)
            data = base / 'data'
            data.write_bytes(b'expected source archive')
            (real / 'source.tar.gz').symlink_to(data)
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                archive.export([self.entry()], real)

    def test_corrupt_export_never_publishes_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            def export_bad(arguments, **_):
                Path(arguments[-1]).write_bytes(b'corrupt fossil content')
            with mock.patch.object(archive.subprocess, 'run', side_effect=export_bad):
                with self.assertRaisesRegex(RuntimeError, 'Corrupt Fossil artifact'):
                    archive.export([self.entry()], cache)
            self.assertEqual(list(cache.iterdir()), [])

    def test_manifest_rejects_path_traversal_and_digest_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            entry = self.entry()
            entry['name'] = '../source.tar.gz'
            path.write_text(json.dumps({'schema': 1, 'artifacts': [entry]}))
            with self.assertRaises(RuntimeError):
                archive.load_manifest(path)
            entry = self.entry()
            entry['artifact'] = 'mutable/latest/source.tar.gz'
            path.write_text(json.dumps({'schema': 1, 'artifacts': [entry]}))
            with self.assertRaises(RuntimeError):
                archive.load_manifest(path)


if __name__ == '__main__':
    unittest.main()
