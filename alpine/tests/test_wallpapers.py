import contextlib
import binascii
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
import zlib
from unittest import mock

REPO = Path(__file__).resolve().parents[2]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


art = load('wallpapers', REPO / 'alpine/desktop/.local/bin/mbp-intel-wallpaper')
generator = load('art_generator', REPO / 'alpine/wallpapers/generate.py')
cron = load('art_cron', REPO / 'alpine/bin/install-wallpaper-schedule')


class WallpaperTests(unittest.TestCase):
    def test_cron_keeps_unrelated_jobs_and_is_idempotent(self):
        previous = 'MAILTO=jack\n5 3 * * * backup-home\n'
        updated = cron.update_crontab(previous, 'generate-ghosts')
        self.assertIn(previous, updated)
        self.assertEqual(updated, cron.update_crontab(updated, 'generate-ghosts'))
        self.assertEqual(previous.strip(), cron.update_crontab(updated).strip())
        self.assertEqual(updated.count('17 * * * *'), 1)

    def test_rejects_malformed_cron_block(self):
        with self.assertRaises(RuntimeError):
            cron.update_crontab('important job\n' + cron.BEGIN)

    def test_generation_environment_excludes_api_keys_and_session_overrides(self):
        with mock.patch.dict(os.environ, {'OPENAI_API_KEY': 'secret', 'CODEX_HOME': '/other',
                                        'ANTHROPIC_API_KEY': 'secret', 'SWAYSOCK': '/other'}):
            env = generator.clean_environment()
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        self.assertNotIn('SWAYSOCK', env)
        self.assertEqual(env['CODEX_HOME'], str(Path.home() / '.codex'))

    def test_reserved_day_never_launches_codex_again(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            today = generator.dt.date.today().isoformat()
            (state / (today + '.json')).write_text('{"status":"failed"}')
            with mock.patch.object(generator, 'STATE', state), mock.patch.object(generator.subprocess, 'run') as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(generator.run_once(), 0)
                run.assert_not_called()

    def test_generated_image_must_be_new_native_landscape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'output.png'
            def chunk(kind, payload):
                return (struct.pack('>I', len(payload)) + kind + payload
                        + struct.pack('>I', binascii.crc32(kind + payload)))
            data = (b'\x89PNG\r\n\x1a\n'
                    + chunk(b'IHDR', struct.pack('>IIBBBBB', 1600, 1000, 8, 2, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress(b'\0' * (1600 * 3 + 1) * 1000, level=0))
                    + chunk(b'IEND', b''))
            image.write_bytes(data)
            self.assertEqual(generator.validate_image(image, root, time.time())[1:], (1600, 1000))
            with self.assertRaises(RuntimeError):
                generator.validate_image(image, root / 'different', time.time())
            with self.assertRaises(RuntimeError):
                generator.validate_image(image, root, time.time() + 10)
            link = root / 'linked.png'
            link.symlink_to(image)
            with self.assertRaises(RuntimeError):
                generator.validate_image(link, root, time.time())
            image.write_bytes(data[:-12])
            with self.assertRaises(RuntimeError):
                generator.validate_image(image, root, time.time())
            image.write_bytes(data[:100] + b'x' + data[101:])
            with self.assertRaises(RuntimeError):
                generator.validate_image(image, root, time.time())

    def test_gallery_rejects_traversal_and_modified_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'alpine/wallpapers').mkdir(parents=True)
            (root / 'alpine/assets').mkdir()
            (root / 'outside.png').write_bytes(b'private')
            (root / 'alpine/assets/good.png').write_bytes(b'image')
            entries = [
                {'id': 'good', 'title': 'Good', 'file': 'alpine/assets/good.png'},
                {'id': 'escape', 'file': 'outside.png'},
                {'id': 'changed', 'file': 'alpine/assets/good.png', 'sha256': 'wrong'}]
            (root / 'alpine/wallpapers/gallery.json').write_text(json.dumps({'entries': entries}))
            with contextlib.redirect_stderr(io.StringIO()):
                found, interval = art.load_gallery(root)
            self.assertEqual([entry['id'] for entry in found], ['good'])
            self.assertEqual(interval, 1200)

    def test_pause_preserves_art_and_next_updates_only_after_sway_success(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            entries = [{'id': 'a', 'title': 'First'}, {'id': 'b', 'title': 'Next'}]
            (state / 'state.json').write_text(json.dumps({'id': 'a', 'title': 'First'}))
            with mock.patch.object(art, 'STATE', state), mock.patch.object(art, 'current_scope', return_value='global'), mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)):
                art.update('pause')
                self.assertTrue(art.read_state()['paused'])
                self.assertEqual(art.read_state()['id'], 'a')
                with mock.patch.object(art, 'apply', side_effect=RuntimeError('no Sway')):
                    with self.assertRaises(RuntimeError):
                        art.update('next')
                self.assertEqual(art.read_state()['id'], 'a')
                with mock.patch.object(art, 'apply', return_value='/owned/socket'):
                    art.update('next')
                self.assertEqual(art.read_state()['id'], 'b')
                self.assertTrue(art.read_state()['paused'])

    def test_workspace_rotation_restores_image_pause_and_timer_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            current = state / 'current.png'
            current.touch()
            entries = [{'id': 'a', 'title': 'First', 'rotate': False},
                       {'id': 'b', 'title': 'Second', 'rotate': False},
                       {'id': 'c', 'title': 'Third', 'rotate': True}]
            with mock.patch.object(art, 'STATE', state), mock.patch.object(art, 'CURRENT', current), \
                    mock.patch.object(art, 'current_scope', return_value='1') as scope, \
                    mock.patch.object(art, 'load_gallery', return_value=(entries, 1200)), \
                    mock.patch.object(art, 'sway_socket', return_value='/owned/socket'), \
                    mock.patch.object(art, 'apply', return_value='/owned/socket'):
                art.update('refresh')
                self.assertEqual(art.read_state()['id'], 'a')
                art.update('pause')
                deadline = art.read_state()['next_at']
                scope.return_value = '2'
                art.update('tick')
                self.assertEqual(art.read_state()['id'], 'b')
                art.update('next')
                self.assertEqual(art.read_state()['id'], 'c')
                scope.return_value = '1'
                art.update('tick')
                self.assertEqual(art.read_state()['id'], 'a')
                self.assertTrue(art.read_state()['paused'])
                self.assertEqual(art.read_state()['next_at'], deadline)
                scope.return_value = '2'
                self.assertFalse(art.read_state().get('paused', False))
                self.assertEqual(art.read_state()['id'], 'c')
                art.update('tick')
                with mock.patch.object(art.time, 'time', return_value=art.read_state()['next_at'] + 1):
                    art.update('tick')
                self.assertEqual(art.read_state()['id'], 'b')

    def test_native_request_is_sandboxed_and_has_no_dangerous_flags(self):
        cmd = generator.codex_command(Path('/tmp/example'), 'gpt-5.6-luna')
        self.assertIn('workspace-write', cmd)
        self.assertIn('--ignore-user-config', cmd)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', cmd)
        self.assertEqual(cmd[cmd.index('-a') + 1], 'never')


if __name__ == '__main__':
    unittest.main()
