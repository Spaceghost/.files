-- S P A C E G H O S T  /  N V I M  S H E L L
-- Neovim is the terminal's shell and the multiplexer. One instance per session:
--   * `nvim` with no files opens a :terminal shell in the only window.
--   * The first instance also listens on $XDG_RUNTIME_DIR/nvim-spaceghost.sock.
--   * $EDITOR inside any shell is ~/.bin/nvim-remote, which opens files in this
--     instance (via $NVIM or the shared socket) and waits, instead of nesting.
-- Ctrl-\ is the prefix: c new tab shell, s/v split shells, h j k l move,
-- n/p next/previous tab, Ctrl-n leaves terminal mode (Neovim default).
-- Opt out of shell mode for one launch: nvim --cmd 'let g:spaceghost_no_shell=1'

vim.o.number = true
vim.o.relativenumber = true
vim.o.mouse = 'a'
vim.o.hidden = true
vim.o.splitbelow = false
vim.o.termguicolors = true

local uv = vim.uv or vim.loop
local Spaceghost = {}
_G.Spaceghost = Spaceghost

Spaceghost.sock = vim.env.SPACEGHOST_NVIM_SOCK
  or ((vim.env.XDG_RUNTIME_DIR or '/tmp') .. '/nvim-spaceghost.sock')

-- Children of every :terminal edit through this instance.
local remote = vim.fn.expand('~/.bin/nvim-remote')
if uv.fs_stat(remote) then
  vim.env.EDITOR = remote
  vim.env.VISUAL = remote
end
vim.env.SPACEGHOST_NVIM_SOCK = Spaceghost.sock

-- ── Server: the first instance owns the shared socket ─────────────────────────
local function socket_alive(path)
  local ok, chan = pcall(vim.fn.sockconnect, 'pipe', path, { rpc = true })
  if ok and chan > 0 then
    pcall(vim.fn.chanclose, chan)
    return true
  end
  return false
end

function Spaceghost.claim_server()
  if vim.env.NVIM then return false end -- nested inside another instance's terminal
  if uv.fs_stat(Spaceghost.sock) then
    if socket_alive(Spaceghost.sock) then return false end
    os.remove(Spaceghost.sock) -- stale socket from a dead instance
  end
  return pcall(vim.fn.serverstart, Spaceghost.sock)
end

-- ── Remote edit: called by nvim-remote via --remote-expr ──────────────────────
-- Opens `path` (empty string = new scratch buffer), optionally at `line`, and
-- removes `done` when the buffer is deleted so the caller can stop waiting.
function Spaceghost.edit(path, done, line)
  local in_terminal = vim.bo.buftype == 'terminal'
  if path == nil or path == '' then
    vim.cmd(in_terminal and 'aboveleft new' or 'enew')
  else
    local target = vim.fn.fnameescape(path)
    vim.cmd((in_terminal and 'aboveleft split ' or 'edit ') .. target)
  end
  line = tonumber(line)
  if line and line > 0 then
    pcall(vim.api.nvim_win_set_cursor, 0, { line, 0 })
  end
  local buf = vim.api.nvim_get_current_buf()
  if done and done ~= '' then
    vim.bo[buf].bufhidden = 'delete'
    vim.api.nvim_create_autocmd({ 'BufDelete', 'BufWipeout' }, {
      buffer = buf,
      once = true,
      callback = function() os.remove(done) end,
    })
  end
  vim.cmd.stopinsert()
  return buf
end

-- ── Shell mode ────────────────────────────────────────────────────────────────
local shell_cmd = { 'sh', '-c', 'exec zsh || exec fish || exec bash' }

-- Open a shell in the current (empty) buffer. `root` marks the login shell:
-- when it exits, Neovim exits.
function Spaceghost.shell(open, root)
  if open then vim.cmd(open) end
  if vim.api.nvim_buf_get_name(0) ~= '' or vim.bo.modified or vim.bo.buftype ~= '' then
    vim.cmd('enew')
  end
  vim.fn.jobstart(shell_cmd, { term = true })
  vim.b.spaceghost_shell = true
  vim.b.spaceghost_shell_root = root or false
  vim.cmd.startinsert()
end

local group = vim.api.nvim_create_augroup('SpaceghostShell', { clear = true })

vim.api.nvim_create_autocmd('VimEnter', {
  group = group,
  callback = function()
    Spaceghost.claim_server()
    if vim.g.spaceghost_no_shell then return end
    if vim.fn.argc() == 0 and vim.fn.bufnr('$') == 1
      and vim.api.nvim_buf_get_name(0) == '' and not vim.bo.modified then
      Spaceghost.shell(nil, true)
    end
  end,
})

vim.api.nvim_create_autocmd('TermOpen', {
  group = group,
  callback = function()
    vim.wo.number = false
    vim.wo.relativenumber = false
    vim.wo.signcolumn = 'no'
  end,
})

-- Land in insert mode when focusing a terminal window.
vim.api.nvim_create_autocmd({ 'BufEnter', 'WinEnter' }, {
  group = group,
  pattern = 'term://*',
  callback = function()
    if vim.bo.buftype == 'terminal' and vim.b.spaceghost_shell then vim.cmd.startinsert() end
  end,
})

-- A finished shell closes its buffer; the root shell closes Neovim.
vim.api.nvim_create_autocmd('TermClose', {
  group = group,
  callback = function(ev)
    if not vim.b[ev.buf].spaceghost_shell then return end
    local root = vim.b[ev.buf].spaceghost_shell_root
    vim.schedule(function()
      if root and pcall(vim.cmd, 'quitall') then return end
      if vim.api.nvim_buf_is_valid(ev.buf) then
        pcall(vim.api.nvim_buf_delete, ev.buf, { force = true })
      end
    end)
  end,
})

-- ── Ctrl-\ prefix: multiplexer controls from any mode ─────────────────────────
local function map(lhs, rhs, desc)
  vim.keymap.set({ 'n', 't' }, lhs, rhs, { silent = true, desc = desc })
end
map('<C-\\>c', function() Spaceghost.shell('tabnew') end, 'New tab shell')
map('<C-\\>s', function() Spaceghost.shell('belowright new') end, 'Split shell below')
map('<C-\\>v', function() Spaceghost.shell('vnew') end, 'Split shell right')
map('<C-\\>h', '<C-\\><C-n><C-w>h', 'Focus left')
map('<C-\\>j', '<C-\\><C-n><C-w>j', 'Focus down')
map('<C-\\>k', '<C-\\><C-n><C-w>k', 'Focus up')
map('<C-\\>l', '<C-\\><C-n><C-w>l', 'Focus right')
map('<C-\\>n', '<C-\\><C-n>gt', 'Next tab')
map('<C-\\>p', '<C-\\><C-n>gT', 'Previous tab')
map('<C-\\>z', '<C-\\><C-n><C-w>_<C-w>|', 'Zoom window')
map('<C-\\>=', '<C-\\><C-n><C-w>=', 'Balance windows')

vim.api.nvim_create_user_command('Shell', function(opts)
  Spaceghost.shell(opts.args ~= '' and opts.args or 'belowright new')
end, { nargs = '?', desc = 'Open a shell: :Shell [tabnew|vnew|new]' })
