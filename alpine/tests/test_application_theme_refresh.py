"""Theme refresh keeps real btop and Neovim processes and editing state alive."""
import fcntl
import json
import os
from pathlib import Path
import pty
import runpy
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest import mock
from theme_fixtures import theme_profile


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'alpine/desktop/.local/bin/oldbook-refresh-application-theme'


class ApplicationThemeRefresh(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='oldbook-app-theme-')
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.config = self.home / '.config'
        self.config.mkdir()
        self.environment = {
            **os.environ, 'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.config),
            'XDG_DATA_HOME': str(self.home / 'data'),
            'XDG_STATE_HOME': str(self.home / 'state'),
            'XDG_CACHE_HOME': str(self.home / 'cache'),
            'NVIM_APPNAME': 'nvim', 'TERM': 'xterm-256color', 'LANG': 'C.UTF-8',
        }

    def refresh(self, process):
        result = subprocess.run(
            [sys.executable, str(HELPER), '--pid', str(process.pid)],
            env=self.environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def start_nvim(self, profile='gruvbox-dark'):
        config = self.config / 'nvim'
        config.mkdir()
        shutil.copytree(REPO / f'alpine/themes/profiles/{profile}/.config/nvim',
                        config, dirs_exist_ok=True)
        self.socket = self.home / "editor's socket"
        process = subprocess.Popen(
            ['nvim', '--headless', '--listen', str(self.socket)],
            env=self.environment, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_process, process)
        deadline = time.monotonic() + 5
        while not self.socket.is_socket():
            self.assertIsNone(process.poll(), 'Neovim exited during startup')
            if time.monotonic() >= deadline:
                self.fail('Neovim did not open its RPC socket')
            time.sleep(0.02)
        while self.remote('vim.v.vim_did_enter') != '1':
            if time.monotonic() >= deadline:
                self.fail('Neovim did not finish loading its startup theme')
            time.sleep(0.02)
        return process

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdin:
            process.stdin.close()

    def remote(self, lua):
        expression = "luaeval('" + lua.replace("'", "''") + "')"
        result = subprocess.run(
            ['nvim', '--server', str(self.socket), '--remote-expr', expression],
            env=self.environment, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def editor_state(self):
        return json.loads(self.remote('''vim.json.encode({
            lines=vim.api.nvim_buf_get_lines(0,0,-1,false),
            modified=vim.bo.modified, cursor=vim.api.nvim_win_get_cursor(0),
            windows=#vim.api.nvim_list_wins(), number=vim.wo.number,
            mode=vim.api.nvim_get_mode().mode,
            undo=vim.fn.undotree().seq_cur,
            mapping=vim.fn.maparg("<Space>w", "n")
        })'''))

    @unittest.skipUnless(shutil.which('nvim'), 'Neovim is not installed')
    def test_nvim_refreshes_theme_without_changing_unsaved_editing_state(self):
        # Missing RPC reload leaves Normal on the previous theme. Sourcing the
        # whole init instead would also reset number and the user's mapping.
        process = self.start_nvim()
        self.remote('''(function()
            vim.api.nvim_buf_set_lines(0,0,-1,false,{"unsaved first", "unsaved second"})
            vim.cmd.vsplit()
            vim.api.nvim_win_set_cursor(0,{2,4})
            vim.wo.number=false
            vim.keymap.set("n", "<Space>w", "<cmd>echo 7<cr>")
            vim.api.nvim_input("i")
            return true
        end)()''')
        before = self.editor_state()
        self.assertEqual(before['mode'], 'i')
        self.assertEqual(self.remote('vim.api.nvim_get_hl(0,{name="Normal"}).bg'),
                         str(0x282828))
        source = theme_profile('spaceghost') / '.config/nvim/init.lua'
        deployed = self.config / 'nvim/init.lua'
        deployed.unlink()
        deployed.symlink_to(source)
        self.refresh(process)
        self.assertEqual(self.remote('vim.api.nvim_get_hl(0,{name="Normal"}).bg'),
                         str(0x13091f))
        self.assertEqual(self.editor_state(), before)
        self.assertIsNone(process.poll())

    @unittest.skipUnless(shutil.which('nvim'), 'Neovim is not installed')
    def test_nvim_rereads_changed_colors_when_the_scheme_name_stays_the_same(self):
        process = self.start_nvim()
        colors = self.config / 'nvim/colors/gruvbox-dark.lua'
        colors.write_text(colors.read_text().replace('#282828', '#123456'))
        self.refresh(process)
        self.assertEqual(self.remote('vim.api.nvim_get_hl(0,{name="Normal"}).bg'),
                         str(0x123456))
        self.assertIsNone(process.poll())

    @unittest.skipUnless(shutil.which('nvim'), 'Neovim is not installed')
    def test_desktop_refresh_reaches_the_existing_neovim_session(self):
        # Omitting the helper from refresh_session leaves a successfully
        # selected theme unapplied in the editor despite a working helper.
        process = self.start_nvim()
        colors = self.config / 'nvim/colors/gruvbox-dark.lua'
        colors.write_text(colors.read_text().replace('#282828', '#234567'))
        theme = runpy.run_path(str(REPO / 'alpine/desktop/.local/bin/oldbook-theme'))
        refresh = theme['refresh_session']

        def private_processes(*names):
            return iter([process.pid] if 'nvim' in names else [])

        # The desktop boundary is external to this isolated editor test. Keep
        # process discovery strictly scoped to our child and other apps inert.
        with mock.patch.dict(refresh.__globals__, {
                'owned_processes': private_processes,
                'sway_reload': lambda: None,
                'run': lambda *args, **kwargs: True,
                'signal_processes': lambda *args: 0,
                'tmux_reload': lambda: 0}):
            refresh()
        self.assertEqual(self.remote('vim.api.nvim_get_hl(0,{name="Normal"}).bg'),
                         str(0x234567))
        self.assertIsNone(process.poll())

    @staticmethod
    def read_until(descriptor, needle, timeout=5):
        output = b''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([descriptor], [], [], 0.05)[0]:
                output += os.read(descriptor, 65536)
                if needle in output:
                    return output
        raise AssertionError(f'btop did not emit {needle!r}; output bytes={len(output)}')

    @unittest.skipUnless(shutil.which('btop'), 'btop is not installed')
    def test_btop_rereads_replaced_theme_symlinks_in_the_same_process(self):
        # Missing SIGUSR2 leaves btop emitting the initial theme's background.
        config = self.config / 'btop'
        (config / 'themes').mkdir(parents=True)
        first = self.home / 'first.theme'
        second = self.home / 'second.theme'
        first.write_text('theme[main_bg]="#123456"\ntheme[main_fg]="#eeeeee"\n')
        second.write_text('theme[main_bg]="#654321"\ntheme[main_fg]="#eeeeee"\n')
        active = config / 'themes/active.theme'
        active.symlink_to(first)
        (config / 'btop.conf').write_text(
            'color_theme = "active"\ntruecolor = true\ntheme_background = true\n'
            'shown_boxes = "cpu"\nupdate_ms = 100\ncheck_temp = false\n')
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
        process = subprocess.Popen(
            ['btop', '--force-utf'], env=self.environment, stdin=slave,
            stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        self.addCleanup(self.stop_process, process)
        self.read_until(master, b'48;2;18;52;86m')
        active.unlink()
        active.symlink_to(second)
        self.refresh(process)
        self.read_until(master, b'48;2;101;67;33m')
        self.assertIsNone(process.poll())


if __name__ == '__main__':
    unittest.main()
