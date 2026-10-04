-- Ctrl-\ prefix: multiplexer controls usable from normal and terminal mode.
local M = {}
local shell = require('spaceghost.shell')

local function map(lhs, rhs, desc, modes)
  vim.keymap.set(modes or { 'n', 't' }, '<C-\\>' .. lhs, rhs, { silent = true, desc = desc })
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
  map('c', function() shell.open('tabnew') end, 'New tab shell')
  map('s', function() shell.open('belowright new') end, 'Split shell below')
  map('v', function() shell.open('belowright vnew') end, 'Split shell right')
  map('x', M.close_pane, 'Close pane')
  map('e', M.edit_prompt, 'Edit a file')
  map('a', M.attach_prompt, 'Attach to a machine in a split')
  for _, k in ipairs({ 'h', 'j', 'k', 'l' }) do
    map(k, '<C-\\><C-n><C-w>' .. k, 'Focus pane ' .. k)
  end
  map('H', '<C-\\><C-n>5<C-w><', 'Resize left')
  map('J', '<C-\\><C-n>3<C-w>-', 'Resize down')
  map('K', '<C-\\><C-n>3<C-w>+', 'Resize up')
  map('L', '<C-\\><C-n>5<C-w>>', 'Resize right')
  map('n', '<C-\\><C-n>gt', 'Next tab')
  map('p', '<C-\\><C-n>gT', 'Previous tab')
  for i = 1, 9 do map(tostring(i), '<C-\\><C-n>' .. i .. 'gt', 'Tab ' .. i) end
  map('<Tab>', '<C-\\><C-n><C-w>p', 'Last pane')
  map('z', M.zoom, 'Zoom pane')
  map('=', '<C-\\><C-n><C-w>=', 'Balance panes')
  map('<Space>', deck.command_deck, 'Command deck')
  map('?', deck.field_guide, 'Field guide')
  map('<F1>', deck.field_guide, 'Field guide')
  map('w', deck.choose_window, 'Tabs + panes')
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
  map('<C-\\>', '<C-\\>', 'Send literal Ctrl-\\', { 't' })
  -- Terminal copy mode: y yanks and returns to the shell prompt.
  vim.keymap.set('n', '<Esc>', function()
    if vim.bo.buftype == 'terminal' and (vim.b.spaceghost_shell or vim.b.spaceghost_float) then vim.cmd.startinsert() end
  end, { desc = 'Back to the shell' })
end

return M
