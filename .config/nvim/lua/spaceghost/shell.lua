-- Shell mode: Neovim as the terminal's shell and multiplexer.
local M = {}
local uv = vim.uv or vim.loop
local native = require('spaceghost.native')

-- First login shell that exists on this machine; `exec a || exec b` in sh exits
-- on the first failure, so pick here instead.
local function pick_shell()
  for _, name in ipairs({ 'zsh', 'fish', 'bash', 'sh' }) do
    local path = vim.fn.exepath(name)
    if path ~= '' then return { path } end
  end
  return { vim.o.shell }
end
M.shell_cmd = pick_shell()
M.sock = vim.env.SPACEGHOST_NVIM_SOCK
  or (vim.env.XDG_RUNTIME_DIR and (vim.env.XDG_RUNTIME_DIR .. '/nvim-spaceghost.sock'))
  or ('/tmp/nvim-spaceghost-' .. tostring(uv.getuid()) .. '.sock')

-- ── Server: the first instance owns the shared socket ─────────────────────────
local function socket_alive(path)
  local ok, chan = pcall(vim.fn.sockconnect, 'pipe', path, { rpc = true })
  if ok and chan > 0 then pcall(vim.fn.chanclose, chan); return true end
  return false
end

function M.claim_server()
  if vim.env.NVIM then return false end
  if vim.tbl_contains(vim.fn.serverlist(), M.sock) then M.is_server = true; return true end
  if uv.fs_stat(M.sock) then
    if socket_alive(M.sock) then return false end
    os.remove(M.sock)
  end
  local ok = pcall(vim.fn.serverstart, M.sock)
  M.is_server = ok
  return ok
end

-- ── Terminal cwd / title / activity bookkeeping ───────────────────────────────
-- cwd of a terminal buffer (from OSC 7), else Neovim's cwd.
function M.cwd(buf)
  buf = buf or 0
  local c = vim.b[buf].spaceghost_cwd
  if c and uv.fs_stat(c) then return c end
  return vim.fn.getcwd()
end

function M.is_shell(buf) return vim.bo[buf].buftype == 'terminal' end

-- Human label for a buffer: terminal title without user@host, else file name.
function M.label(buf)
  if vim.b[buf].spaceghost_attach then return '@' .. vim.b[buf].spaceghost_attach end
  if vim.bo[buf].buftype == 'terminal' then
    local title = vim.b[buf].term_title or ''
    title = title:gsub('^[%w%.%-_]+@[%w%.%-_]+:%s*', '')
    if title == '' or title:match('^[~/]') or title:match('^z?sh$') then
      return vim.fn.fnamemodify(M.cwd(buf), ':t')
    end
    return title
  end
  local name = vim.api.nvim_buf_get_name(buf)
  if name == '' then return '[scratch]' end
  return vim.fn.fnamemodify(name, ':t')
end

local function visible_in_current_tab(buf)
  for _, w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if vim.api.nvim_win_get_buf(w) == buf then return true end
  end
  return false
end

local function watch_activity(buf)
  vim.api.nvim_buf_attach(buf, false, {
    on_lines = function()
      if not vim.api.nvim_buf_is_valid(buf) then return true end
      if not visible_in_current_tab(buf) and not vim.b[buf].spaceghost_new then
        vim.b[buf].spaceghost_new = true
        vim.schedule(function() pcall(vim.cmd.redrawtabline) end)
      end
    end,
  })
end

-- ── Opening shells ────────────────────────────────────────────────────────────
-- open: nil (current empty buffer) | 'tabnew' | 'new' | 'vnew' | any window command.
function M.open(open, opts)
  opts = opts or {}
  local cwd = opts.cwd or M.cwd(0)
  if open then vim.cmd(open) end
  if vim.api.nvim_buf_get_name(0) ~= '' or vim.bo.modified or vim.bo.buftype ~= '' then
    vim.cmd('enew')
  end
  vim.fn.jobstart(opts.cmd or M.shell_cmd, { term = true, cwd = cwd })
  vim.b.spaceghost_shell = true
  vim.b.spaceghost_shell_root = opts.root or false
  vim.b.spaceghost_cwd = cwd
  vim.cmd.startinsert()
  return vim.api.nvim_get_current_buf()
end

-- Floating terminal; `key` makes it persistent (toggle) across calls.
local floats = {}
function M.float(cmd, opts)
  opts = opts or {}
  local key = opts.key
  local state = key and floats[key]
  if state and vim.api.nvim_win_is_valid(state.win) then
    vim.api.nvim_win_hide(state.win)
    return
  end
  local cols, lines = vim.o.columns, vim.o.lines - vim.o.cmdheight - 2
  local w = math.floor(cols * (opts.width or 0.85))
  local h = math.floor(lines * (opts.height or 0.75))
  local buf
  if state and vim.api.nvim_buf_is_valid(state.buf) then
    buf = state.buf
  else
    buf = vim.api.nvim_create_buf(false, true)
  end
  local win = vim.api.nvim_open_win(buf, true, {
    relative = 'editor', width = w, height = h,
    row = math.floor((lines - h) / 2), col = math.floor((cols - w) / 2),
    style = 'minimal', border = 'rounded',
    title = ' SPACEGHOST / ' .. (opts.title or 'terminal') .. ' ', title_pos = 'center',
  })
  vim.wo[win].winhighlight = 'Normal:NormalFloat,FloatBorder:FloatBorder,FloatTitle:FloatTitle'
  if not (state and vim.api.nvim_buf_is_valid(state.buf)) then
    vim.fn.jobstart(cmd or M.shell_cmd, {
      term = true, cwd = opts.cwd or M.cwd(0),
      on_exit = function()
        vim.schedule(function()
          if key then floats[key] = nil end
          if vim.api.nvim_win_is_valid(win) then vim.api.nvim_win_close(win, true) end
          if vim.api.nvim_buf_is_valid(buf) then pcall(vim.api.nvim_buf_delete, buf, { force = true }) end
        end)
      end,
    })
    vim.b[buf].spaceghost_float = true
    vim.b[buf].spaceghost_cwd = opts.cwd or M.cwd(0)
  end
  if key then floats[key] = { buf = buf, win = win } end
  vim.cmd.startinsert()
  return buf, win
end

-- ── Attach to another machine's session in a pane ─────────────────────────────
-- Runs `nvim-attach --here HOST` (mosh or ssh UI client) inside a terminal split.
-- Ctrl-\ in that pane goes to the remote cockpit; Alt-\ steps back out here.
function M.attach(host, open)
  if not host or host == '' then return M.open(open or 'belowright vnew') end
  local buf = M.open(open or 'belowright vnew', {
    cmd = { vim.fn.expand('~/.bin/nvim-attach'), '--here', host },
    cwd = vim.env.HOME,
  })
  vim.b[buf].spaceghost_attach = host
  vim.b[buf].term_title = host
  vim.keymap.set('t', '<C-\\>', '<C-\\>', { buffer = buf, nowait = true, desc = 'Prefix goes to ' .. host })
  vim.keymap.set('t', '<M-\\>', '<C-\\><C-n>', { buffer = buf, nowait = true, desc = 'Back to the local cockpit' })
  return buf
end

-- ── Remote edit: used by ~/.bin/nvim-remote via --remote-expr ─────────────────
function M.edit(path, done, line)
  local in_terminal = vim.bo.buftype == 'terminal'
  if path == nil or path == '' then
    vim.cmd(in_terminal and 'aboveleft new' or 'enew')
  else
    vim.cmd((in_terminal and 'aboveleft split ' or 'edit ') .. vim.fn.fnameescape(path))
  end
  line = tonumber(line)
  if line and line > 0 then pcall(vim.api.nvim_win_set_cursor, 0, { line, 0 }) end
  local buf = vim.api.nvim_get_current_buf()
  if done and done ~= '' then
    vim.bo[buf].bufhidden = 'delete'
    vim.api.nvim_create_autocmd({ 'BufDelete', 'BufWipeout' }, {
      buffer = buf, once = true, callback = function() os.remove(done) end,
    })
  end
  vim.cmd.stopinsert()
  return buf
end

-- ── Autocommands ──────────────────────────────────────────────────────────────
function M.setup()
  local remote = vim.fn.expand('~/.bin/nvim-remote')
  if uv.fs_stat(remote) then vim.env.EDITOR = remote; vim.env.VISUAL = remote end
  vim.env.SPACEGHOST_NVIM_SOCK = M.sock

  local group = vim.api.nvim_create_augroup('SpaceghostShell', { clear = true })

  vim.api.nvim_create_autocmd('VimEnter', {
    group = group,
    callback = function()
      M.claim_server()
      if vim.g.spaceghost_no_shell then return end
      if vim.fn.argc() == 0 and vim.fn.bufnr('$') == 1
        and vim.api.nvim_buf_get_name(0) == '' and not vim.bo.modified then
        M.open(nil, { root = true, cwd = vim.fn.getcwd() })
      end
    end,
  })

  vim.api.nvim_create_autocmd('TermOpen', {
    group = group,
    callback = function(ev)
      vim.wo.number = false
      vim.wo.relativenumber = false
      vim.wo.signcolumn = 'no'
      vim.wo.cursorline = false
      watch_activity(ev.buf)
    end,
  })

  -- OSC 7 from the shell keeps b:spaceghost_cwd current (zsh precmd in .zshrc).
  vim.api.nvim_create_autocmd('TermRequest', {
    group = group,
    callback = function(ev)
      local seq = type(ev.data) == 'table' and ev.data.sequence or ev.data
      if type(seq) ~= 'string' then return end
      local path = native.osc7_path(seq)
      if path then
        vim.b[ev.buf].spaceghost_cwd = path
        vim.schedule(function() pcall(vim.cmd.redrawtabline); pcall(vim.cmd.redrawstatus) end)
      end
    end,
  })

  vim.api.nvim_create_autocmd({ 'BufEnter', 'WinEnter' }, {
    group = group,
    callback = function(ev)
      if vim.bo[ev.buf].buftype ~= 'terminal' then return end
      if vim.b[ev.buf].spaceghost_new then
        vim.b[ev.buf].spaceghost_new = false
        vim.schedule(function() pcall(vim.cmd.redrawtabline) end)
      end
      if vim.b[ev.buf].spaceghost_shell or vim.b[ev.buf].spaceghost_float then vim.cmd.startinsert() end
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

  vim.api.nvim_create_user_command('Shell', function(opts)
    M.open(opts.args ~= '' and opts.args or 'belowright new')
  end, { nargs = '?', desc = 'Open a shell: :Shell [tabnew|vnew|new]' })
  vim.api.nvim_create_user_command('Attach', function(opts)
    local host, open = opts.fargs[1], opts.fargs[2]
    M.attach(host, open and ({ tabnew = 'tabnew', new = 'belowright new', vnew = 'belowright vnew' })[open] or open)
  end, { nargs = '+', desc = 'Attach to HOST in a pane: :Attach HOST [vnew|new|tabnew]' })
end

return M
