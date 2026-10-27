-- Prefix keys: multiplexer controls usable from normal and terminal mode.
-- Ctrl-\ everywhere; Ctrl-Space in terminals that report it as a key (kitty
-- keyboard protocol: Ghostty, foot, kitty, Alacritty, WezTerm). Override with
-- vim.g.spaceghost_prefixes = { '<C-\\>', '<C-Space>', '<C-b>' } before setup.
local M = {}
local shell = require('spaceghost.shell')

M.prefixes = vim.g.spaceghost_prefixes or { '<C-\\>', '<C-Space>' }
M.direct_keys = {}
M.prefixed_keys = {}

local function map(lhs, rhs, desc, modes)
  for _, prefix in ipairs(M.prefixes) do
    local key = prefix .. lhs
    vim.keymap.set(modes or { 'n', 't' }, key, rhs, { silent = true, desc = desc })
    M.prefixed_keys[#M.prefixed_keys + 1] = key
  end
end

-- Window IDs are global: unlike <C-w>p, this also remembers other tabs.
-- Keep the history across configuration reloads and ignore floating menus.
local function remember_pane()
  local win = vim.api.nvim_get_current_win()
  if vim.api.nvim_win_get_config(win).relative ~= '' then return end
  local history = { win }
  for _, old in ipairs(vim.g.spaceghost_pane_history or {}) do
    if old ~= win and vim.api.nvim_win_is_valid(old) then history[#history + 1] = old end
  end
  vim.g.spaceghost_pane_history = history
end

function M.previous_pane()
  local current = vim.api.nvim_get_current_win()
  for _, win in ipairs(vim.g.spaceghost_pane_history or {}) do
    if win ~= current and vim.api.nvim_win_is_valid(win) then
      vim.api.nvim_set_current_win(win)
      return
    end
  end
end

function M.focus_tab(delta)
  local tabs = vim.api.nvim_list_tabpages()
  local index = vim.api.nvim_tabpage_get_number(0)
  vim.api.nvim_set_current_tabpage(tabs[(index - 1 + delta) % #tabs + 1])
end

function M.focus_pane(direction)
  vim.cmd.wincmd(direction)
end

function M.zoom()
  if vim.t.spaceghost_zoom then
    vim.cmd(vim.t.spaceghost_zoom)
    vim.t.spaceghost_zoom = nil
  else
    if #vim.api.nvim_tabpage_list_wins(0) == 1 then return end
    vim.t.spaceghost_zoom = vim.fn.winrestcmd()
    vim.cmd('wincmd _ | wincmd |')
  end
  vim.cmd.redrawtabline()
end

function M.close_pane()
  local buf = vim.api.nvim_get_current_buf()
  if vim.bo[buf].buftype == 'terminal' then
    -- Multiple panes can display one terminal job. Remove only this view;
    -- deleting the shared buffer would stop the job and clear every view.
    if #vim.fn.win_findbuf(buf) > 1 then
      vim.api.nvim_win_close(0, false)
      return
    end
    if vim.b[buf].spaceghost_shell_root and #vim.api.nvim_list_wins() == 1 then
      vim.cmd('quitall')
      return
    end
    pcall(vim.api.nvim_buf_delete, buf, { force = true })
  else
    pcall(vim.cmd, 'close')
  end
end

function M.edit_prompt()
  vim.ui.input({ prompt = 'Edit: ', default = shell.cwd(0) .. '/', completion = 'file' }, function(path)
    if not path or path == '' then return end
    shell.edit(vim.fn.expand(path))
  end)
end

function M.attach_prompt()
  vim.ui.input({ prompt = 'Attach to host: ', default = vim.g.spaceghost_last_host or '' }, function(host)
    if not host or host == '' then return end
    vim.g.spaceghost_last_host = host
    shell.attach(host)
  end)
end

function M.setup()
  local deck = require('spaceghost.deck')
  M.direct_keys = {}
  M.prefixed_keys = {}
  local group = vim.api.nvim_create_augroup('SpaceghostNavigation', { clear = true })
  vim.api.nvim_create_autocmd('WinEnter', { group = group, callback = remember_pane })
  remember_pane()
  map('c', function() shell.open('tabnew') end, 'New tab shell')
  map('s', function() shell.open('belowright new') end, 'Split shell below')
  map('v', function() shell.open('belowright vnew') end, 'Split shell right')
  map('x', M.close_pane, 'Close pane')
  map('d', shell.redraw, 'Redraw pane')
  map('e', M.edit_prompt, 'Edit a file')
  map('a', M.attach_prompt, 'Attach to a machine in a split')
  map('i', function() require('spaceghost.agent').run('toggle') end, 'Native Codex chat', { 'n', 'i', 'v' })
  map('i', '<C-\\><C-n><Cmd>Codex<CR>', 'Native Codex chat', { 't' })
  map('o', '<Cmd>CodexWorkers<CR>', 'Codex worker dashboard', { 'n', 'i', 'v' })
  map('o', '<C-\\><C-n><Cmd>CodexWorkers<CR>', 'Codex worker dashboard', { 't' })
  map('I', function() require('spaceghost.agent').run('add_selection_or_file_to_context') end, 'Add file or selection to Codex', { 'n', 'v' })
  for _, k in ipairs({ 'h', 'j', 'k', 'l' }) do
    map(k, function() M.focus_pane(k) end, 'Focus pane ' .. k)
  end
  for _, key in ipairs({ 'Left', 'Down', 'Up', 'Right' }) do
    -- Remove the old Alt-arrow bindings when upgrading a running session.
    -- These keys belong to terminal programs, including Codex and readline.
    local alt = '<M-' .. key .. '>'
    for _, mode in ipairs({ 'n', 't' }) do pcall(vim.keymap.del, mode, alt) end
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do
      if vim.b[buf].spaceghost_attach then pcall(vim.keymap.del, 't', alt, { buffer = buf }) end
    end
  end
  map('H', '<C-\\><C-n>5<C-w><', 'Resize left')
  map('J', '<C-\\><C-n>3<C-w>-', 'Resize down')
  map('K', '<C-\\><C-n>3<C-w>+', 'Resize up')
  map('L', '<C-\\><C-n>5<C-w>>', 'Resize right')
  map('n', function() M.focus_tab(1) end, 'Next tab')
  map('p', function() M.focus_tab(-1) end, 'Previous tab')
  map('u', shell.previous_prompt, 'Previous shell prompt', { 't' })
  for i = 1, 9 do
    local function jump()
      local tab = vim.api.nvim_list_tabpages()[i]
      if tab then vim.api.nvim_set_current_tabpage(tab) end
    end
    map(tostring(i), jump, 'Tab ' .. i)
    local key = '<M-' .. i .. '>'
    vim.keymap.set({ 'n', 't' }, key, jump, { desc = 'Tab ' .. i })
    M.direct_keys[#M.direct_keys + 1] = key
  end
  map('<Tab>', M.previous_pane, 'Previous pane (across tabs)')
  map('z', M.zoom, 'Zoom pane')
  map('=', '<C-\\><C-n><C-w>=', 'Balance panes')
  map('<Space>', deck.command_deck, 'Command deck')
  map('?', deck.field_guide, 'Field guide')
  map('<F1>', deck.field_guide, 'Field guide')
  map('w', deck.choose_window, 'Tabs + panes')
  -- Direct navigation, without taking readline's Ctrl-h/j/k/l or plain Esc.
  local direct = {
    { '<F1>', deck.field_guide, 'Field guide' },
    { '<F2>', deck.choose_window, 'Find any tab, pane or host' },
    { '<F4>', deck.command_deck, 'Command deck' },
    { '<C-PageUp>', function() M.focus_tab(-1) end, 'Previous tab' },
    { '<C-PageDown>', function() M.focus_tab(1) end, 'Next tab' },
    { '<M-[>', function() M.focus_tab(-1) end, 'Previous tab' },
    { '<M-]>', function() M.focus_tab(1) end, 'Next tab' },
    { '<M-o>', M.previous_pane, 'Previous pane (across tabs)' },
  }
  for _, binding in ipairs(direct) do
    vim.keymap.set({ 'n', 't' }, binding[1], binding[2], { silent = true, desc = binding[3] })
    M.direct_keys[#M.direct_keys + 1] = binding[1]
  end
  map(',', deck.rename_tab, 'Rename tab')
  map('`', function() shell.float(nil, { key = 'scratch', title = 'scratch terminal' }) end, 'Scratch terminal')
  map('g', deck.git_observatory, 'Git observatory')
  map('~', deck.monitor, 'Process monitor')
  map('r', deck.reload, 'Reload configuration')
  map('[', '<C-\\><C-n>', 'Copy mode (normal mode)', { 't' })
  map(']', function()
    local text = vim.fn.getreg('"')
    if text ~= '' then vim.api.nvim_chan_send(vim.bo.channel, text) end
  end, 'Paste register into shell', { 't' })
  -- Prefix twice sends the prefix itself to the program in the pane.
  for _, prefix in ipairs(M.prefixes) do
    vim.keymap.set('t', prefix .. prefix, prefix, { desc = 'Send literal ' .. prefix })
    M.prefixed_keys[#M.prefixed_keys + 1] = prefix .. prefix
  end
  vim.keymap.set({ 'n', 't' }, '<C-]>', function()
    if vim.b.spaceghost_attach then shell.remote_keys(nil, 'toggle') end
  end, { desc = 'Toggle navigation keys between local and remote' })
  -- Terminal copy mode: y yanks and returns to the shell prompt.
  vim.keymap.set('n', '<Esc>', function()
    if vim.bo.buftype == 'terminal' and (vim.b.spaceghost_shell or vim.b.spaceghost_float) then vim.cmd.startinsert() end
  end, { desc = 'Back to the shell' })
  -- Existing attached panes keep their routing after a config reload.
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.b[buf].spaceghost_attach and vim.b[buf].spaceghost_remote_keys then
      shell.remote_keys(buf, true, true)
    end
  end
end

return M
