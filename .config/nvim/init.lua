-- S P A C E G H O S T  /  N V I M  S H E L L
-- Neovim is the terminal's shell and the multiplexer. One instance per session:
--   * `nvim` with no files opens a :terminal shell in the only window.
--   * The first instance also listens on $XDG_RUNTIME_DIR/nvim-spaceghost.sock.
--   * $EDITOR inside any shell is ~/.bin/nvim-remote, which opens files in this
--     instance (via $NVIM or the shared socket) and waits, instead of nesting.
-- Prefix Ctrl-\ ; Ctrl-\ Space is the command deck, Ctrl-\ ? the field guide.
-- Native HUD helpers: native/spaceghost.nelua built by ~/.bin/spaceghost-native
-- (nelua + zig cc), loaded over FFI with pure Lua fallbacks.
-- Opt out of shell mode for one launch: nvim --cmd 'let g:spaceghost_no_shell=1'
-- Guide: docs/nvim-shell.md in Spaceghost/.files

vim.o.number = true
vim.o.relativenumber = true
vim.o.mouse = 'a'
vim.o.hidden = true
vim.o.termguicolors = true
vim.o.splitbelow = false
vim.o.splitright = true
vim.o.cursorline = true
vim.o.signcolumn = 'yes'
vim.o.scrolloff = 4
vim.o.updatetime = 300
vim.o.timeoutlen = 600
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.undofile = true
vim.o.expandtab = true
vim.o.shiftwidth = 2
vim.o.tabstop = 2
vim.o.wrap = false
vim.o.list = true
vim.o.listchars = 'tab:→ ,trail:·,nbsp:␣'
vim.o.pumheight = 12
vim.o.shortmess = vim.o.shortmess .. 'I'
vim.o.guicursor = 'n-v-c-sm:block,i-ci-ve:ver25,r-cr-o:hor20,t:ver25-blinkon500'
if vim.fn.has('nvim-0.10') == 1 then vim.o.smoothscroll = true end

vim.cmd.colorscheme('spaceghost')

_G.Spaceghost = {
  native = require('spaceghost.native'),
  shell = require('spaceghost.shell'),
  ui = require('spaceghost.ui'),
  deck = require('spaceghost.deck'),
  keys = require('spaceghost.keys'),
}
-- ~/.bin/nvim-remote calls v:lua.Spaceghost.edit(path, done, line)
Spaceghost.edit = Spaceghost.shell.edit
Spaceghost.sock = Spaceghost.shell.sock

Spaceghost.shell.setup()
Spaceghost.ui.setup()
Spaceghost.keys.setup()

-- Treesitter highlighting for buffers whose parser is installed; silent otherwise.
vim.api.nvim_create_autocmd('FileType', {
  callback = function(ev) pcall(vim.treesitter.start, ev.buf) end,
})

-- Yank flash, so copy mode gives feedback inside shells too.
vim.api.nvim_create_autocmd('TextYankPost', {
  callback = function() vim.highlight.on_yank({ higroup = 'Visual', timeout = 120 }) end,
})
