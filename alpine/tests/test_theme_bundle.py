import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[2]


class ThemeBundleTests(unittest.TestCase):
    def setUp(self):
        self.api = runpy.run_path(str(REPO / 'alpine/bin/theme-bundle'))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_roundtrip_keeps_effect_code_and_binary_assets(self):
        source = self.root / 'source'
        themes = source / 'alpine/themes'
        profile = themes / 'profiles/demo'
        effect = profile / '.local/share/oldbook/themes/demo/effect.py'
        effect.parent.mkdir(parents=True)
        effect.write_text('from .helper import color\n')
        effect.with_name('helper.py').write_text('color = "blue"\n')
        effect.with_name('texture.png').write_bytes(b'\x89PNG\r\n\xff')
        (themes / 'demo.json').write_text(json.dumps({
            'id': 'demo', 'name': 'Demo', 'image_style': '',
            'effects': {'ripple': {'module': '.local/share/oldbook/themes/demo/effect.py'}}}))
        archive = self.root / 'demo.zip'
        self.api['export_bundle'](source, 'demo', archive)
        target = self.root / 'target'
        self.api['import_bundle'](target, archive)
        installed = target / 'alpine/themes/profiles/demo' / effect.relative_to(profile)
        self.assertEqual(installed.read_bytes(), effect.read_bytes())
        self.assertEqual(installed.with_name('texture.png').read_bytes(), b'\x89PNG\r\n\xff')
        with self.assertRaises((ValueError, FileExistsError)):
            self.api['import_bundle'](target, archive)

    def test_archive_traversal_is_rejected_without_writing_outside_repo(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../escape', 'bad')
        with self.assertRaises(ValueError):
            self.api['import_bundle'](self.root / 'target', archive)
        self.assertFalse((self.root / 'escape').exists())

    def test_tampered_payload_is_rejected(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('theme.json', '{}')
            z.writestr('manifest.json', json.dumps({'version': 1,
                         'files': {'theme.json': '0' * 64}}))
        with self.assertRaises(ValueError):
            self.api['import_bundle'](self.root / 'target', archive)


if __name__ == '__main__':
    unittest.main()
