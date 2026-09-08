"""Terminal chrome: the fastfetch splash, Ghostty shaders and Neovim statusline."""
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / 'alpine/desktop'
PROFILE = REPO / 'alpine/themes/profiles/gruvbox-dark'
SPLASH = DESKTOP / '.local/bin/oldbook-splash'


def strip_jsonc(text):
    return re.sub(r'^\s*//.*$', '', text, flags=re.MULTILINE)


def tiny_png(width, height, color=(0xfa, 0xbd, 0x2f)):
    """A valid RGB PNG without any image library."""
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    raw = b''.join(b'\x00' + bytes(color) * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


class SharedCopies(unittest.TestCase):
    def test_live_profile_copies_match_the_shared_desktop_files(self):
        for path in ('.zshrc', '.config/nvim/init.lua', '.config/fastfetch/config.jsonc',
                     '.config/fastfetch/ghost.txt'):
            with self.subTest(path=path):
                self.assertEqual((DESKTOP / path).read_text(), (PROFILE / path).read_text())


class Splash(unittest.TestCase):
    def test_zshrc_guard_runs_once_outside_tmux_on_a_tty(self):
        for path in (DESKTOP / '.zshrc', PROFILE / '.zshrc'):
            body = path.read_text()
            guard = re.search(r'if \[\[ (.*oldbook-splash.*) \]\]', body)
            self.assertIsNotNone(guard, path)
            for condition in ('-z $OLDBOOK_SPLASH', '-z $TMUX', '-t 1'):
                self.assertIn(condition, guard.group(1))
            self.assertIn('export OLDBOOK_SPLASH=1', body)
            self.assertLess(body.index('[[ -o interactive ]] || return'), body.index('OLDBOOK_SPLASH'))

    def test_config_is_valid_jsonc_with_theme_colours_and_desktop_state(self):
        document = json.loads(strip_jsonc((DESKTOP / '.config/fastfetch/config.jsonc').read_text()))
        self.assertEqual(document['display']['color']['keys'], '#fabd2f')
        self.assertEqual(set(document['logo']['color']), {'1', '2', '3'})
        commands = [m['text'] for m in document['modules'] if m.get('type') == 'command']
        self.assertTrue(any('fossil branch current' in c for c in commands))
        self.assertTrue(any('wallpaper/state.json' in c for c in commands))
        self.assertTrue(any('scripture/selection.json' in c for c in commands))
        # Header colours follow the theme through placeholders, not hard-coded escapes.
        custom = [m['format'] for m in document['modules'] if m.get('type') == 'custom']
        self.assertTrue(any('{#keys}' in f for f in custom))
        self.assertFalse(any('38;2;' in f for f in custom))
        ghost = (DESKTOP / '.config/fastfetch/ghost.txt').read_text()
        self.assertLessEqual(set(re.findall(r'\$(\d)', ghost)), {'1', '2', '3'})

    def run_splash(self, environment, logo=None):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / 'home'
            bin_dir = Path(temporary) / 'bin'
            bin_dir.mkdir()
            (home / '.local/share/oldbook').mkdir(parents=True)
            (home / '.config/fastfetch').mkdir(parents=True)
            (home / '.config/fastfetch/ghost.txt').write_text('$1 ghost\n')
            if logo is not None:
                (home / '.local/share/oldbook/wallpaper.png').write_bytes(logo)
            recorder = bin_dir / 'fastfetch'
            recorder.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$RECORD"\n')
            recorder.chmod(0o755)
            record = Path(temporary) / 'argv'
            env = {'PATH': f'{bin_dir}:{os.environ["PATH"]}', 'HOME': str(home),
                   'XDG_CACHE_HOME': str(home / '.cache'), 'RECORD': str(record)}
            env.update(environment)
            result = subprocess.run([str(SPLASH), '--pipe', 'false'], env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = record.read_text().splitlines()
            cache = sorted((home / '.cache/oldbook/splash').glob('*')) if (home / '.cache/oldbook/splash').is_dir() else []
            return arguments, [(p.name, p.read_bytes()) for p in cache]

    def test_text_override_uses_the_ghost_text_logo(self):
        arguments, cache = self.run_splash({'OLDBOOK_SPLASH_LOGO': 'text'}, tiny_png(8, 6))
        self.assertEqual(arguments[:2], ['--logo-type', 'file'])
        self.assertTrue(arguments[3].endswith('/.config/fastfetch/ghost.txt'))
        self.assertEqual(arguments[-2:], ['--pipe', 'false'])
        self.assertEqual(cache, [])

    def test_none_override_prints_no_logo(self):
        arguments, _ = self.run_splash({'OLDBOOK_SPLASH_LOGO': 'none'}, tiny_png(8, 6))
        self.assertEqual(arguments[:2], ['--logo-type', 'none'])

    def test_missing_painting_falls_back_to_text(self):
        arguments, _ = self.run_splash({'TERM_PROGRAM': 'ghostty'})
        self.assertEqual(arguments[:2], ['--logo-type', 'file'])

    def test_ghostty_gets_a_kitty_file_reference_not_pixels(self):
        arguments, cache = self.run_splash({'TERM_PROGRAM': 'ghostty'}, tiny_png(16, 10))
        self.assertEqual(arguments[:2], ['--logo-type', 'raw'])
        self.assertEqual(arguments[4:8:2], ['--logo-width', '--logo-height'])
        self.assertEqual(len(cache), 1)
        name, body = cache[0]
        self.assertTrue(name.endswith('.apc'))
        self.assertTrue(body.startswith(b'\x1b_G') and body.endswith(b'\x1b\\'))
        for option in (b'q=2', b'a=T', b't=f', b'f=100', b'C=1'):
            self.assertIn(option, body)
        self.assertLess(len(body), 400)

    def test_sixel_stream_is_cached_and_well_formed(self):
        arguments, cache = self.run_splash({'OLDBOOK_SPLASH_LOGO': 'sixel'}, tiny_png(24, 12))
        self.assertEqual(arguments[:2], ['--logo-type', 'raw'])
        self.assertEqual(len(cache), 1)
        name, body = cache[0]
        self.assertTrue(name.endswith('.sixel'))
        # libsixel or the numpy fallback: a DCS sixel stream with raster attributes.
        self.assertTrue(body.startswith(b'\x1bP') and body.endswith(b'\x1b\\'))
        self.assertRegex(body, rb'q"1;1;\d+;\d+')
        self.assertIn(b'#', body)
        self.assertIn(b'-', body)
        # The cache key depends on the painting bytes, logo cells and cell size only.
        again, cache_again = self.run_splash({'OLDBOOK_SPLASH_LOGO': 'sixel'}, tiny_png(24, 12))
        self.assertEqual(Path(again[3]).name, Path(arguments[3]).name)
        self.assertEqual(cache_again[0][1], body)

    def test_terminal_detection_walks_the_process_tree(self):
        module = runpy.run_path(str(SPLASH), run_name='oldbook_splash')
        self.assertEqual(module['parent_of'](os.getpid()), os.getppid())
        self.assertIn(module['process_name'](os.getpid()), ('python3', 'python3.14', 'python'))

    def test_sixel_encoder_quantises_to_the_colour_cube(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy unavailable')
        module = runpy.run_path(str(SPLASH), run_name='oldbook_splash')
        pixels = np.zeros((6, 4, 3), dtype=np.uint8)
        pixels[:, 2:, :] = 255
        stream = module['encode_sixel'](pixels)
        self.assertTrue(stream.startswith(b'\x1bPq"1;1;4;6'))
        self.assertIn(b'#0', stream)
        self.assertIn(b'#215', stream)
        self.assertTrue(stream.endswith(b'-\x1b\\'))


class GhosttyShaders(unittest.TestCase):
    def test_both_configs_enable_the_same_existing_shaders(self):
        for config in (DESKTOP / '.config/ghostty/config', PROFILE / '.config/ghostty/config'):
            body = config.read_text()
            shaders = re.findall(r'^custom-shader = (.+)$', body, flags=re.MULTILINE)
            self.assertEqual(shaders, ['~/.config/ghostty/shaders/warm-bloom.glsl',
                                       '~/.config/ghostty/shaders/cursor-smear.glsl'], config)
            self.assertIn('custom-shader-animation = true', body)
        for name in ('warm-bloom.glsl', 'cursor-smear.glsl'):
            source = (DESKTOP / '.config/ghostty/shaders' / name).read_text()
            self.assertIn('void mainImage(out vec4 fragColor, in vec2 fragCoord)', source)
            for reserved in ('half', 'sample', 'input', 'output'):
                self.assertNotRegex(source, r'\b' + reserved + r'\b', f'{name} uses reserved word {reserved}')

    def test_shader_lines_survive_the_derived_profile(self):
        theme = runpy.run_path(str(DESKTOP / '.local/bin/oldbook-theme'), run_name='oldbook_theme')
        base = theme['base_ghostty'](REPO)
        self.assertIn('custom-shader = ~/.config/ghostty/shaders/cursor-smear.glsl', base)
        self.assertIn('custom-shader-animation = true', base)


class NeovimChrome(unittest.TestCase):
    def test_init_lua_defines_the_chrome(self):
        body = (DESKTOP / '.config/nvim/init.lua').read_text()
        for needle in ('vim.opt.laststatus = 3', 'oldbook_statusline', 'oldbook_winbar',
                       'vert = "▏"', 'eob = " "', '"OldbookMode" .. name', 'Insert = palette.green'):
            self.assertIn(needle, body)
        self.assertNotIn('require("lazy")', body)
        self.assertNotIn('packer', body)

    @unittest.skipUnless(shutil.which('nvim'), 'nvim unavailable')
    def test_headless_neovim_renders_the_statusline_without_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            sample = Path(temporary) / 'sample.txt'
            sample.write_text('hello\n')
            env = dict(os.environ, XDG_CONFIG_HOME=str(DESKTOP / '.config'),
                       XDG_DATA_HOME=str(Path(temporary) / 'data'), XDG_STATE_HOME=str(Path(temporary) / 'state'))
            result = subprocess.run(
                ['nvim', '--headless', '-c',
                 'lua io.write(_G.oldbook_statusline() .. "\\n" .. _G.oldbook_winbar() .. "\\n")',
                 '-c', 'qa!', str(sample)], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('%#OldbookModeNormal# NORMAL', result.stdout)
        self.assertIn('sample.txt', result.stdout)
        self.assertNotIn('Error', result.stderr)


if __name__ == '__main__':
    unittest.main()
