-- Command deck, field guide, popups. Floating menus with single-key actions.
local M = {}
local shell = require('spaceghost.shell')

-- items: { { key = 'c', label = 'New tab shell', action = fn }, { sep = true }, { note = '...' } }
function M.menu(title, items)
  local lines, maxw = {}, #title + 4
  for _, it in ipairs(items) do
    local line
    if it.sep then line = ''
    elseif it.note then line = '  ' .. it.note
    else line = string.format('  %-6s %s', it.key, it.label) end
    lines[#lines + 1] = line
    if #line + 4 > maxw then maxw = #line + 4 end
  end
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].bufhidden = 'wipe'
  local cols, rows = vim.o.columns, vim.o.lines - vim.o.cmdheight - 2
  local w, h = math.min(maxw, cols - 4), math.min(#lines, rows - 2)
  local win = vim.api.nvim_open_win(buf, true, {
    relative = 'editor', width = w, height = h,
    row = math.floor((rows - h) / 2), col = math.floor((cols - w) / 2),
    style = 'minimal', border = 'rounded', title = ' SPACEGHOST / ' .. title .. ' ', title_pos = 'center',
  })
  vim.wo[win].winhighlight = 'Normal:NormalFloat,FloatBorder:FloatBorder,FloatTitle:FloatTitle,CursorLine:SpaceghostMenuSel'
  vim.wo[win].cursorline = true
  local ns = vim.api.nvim_create_namespace('spaceghost-menu')
  for i, it in ipairs(items) do
    if it.key then
      vim.api.nvim_buf_set_extmark(buf, ns, i - 1, 2, { end_col = 2 + #it.key, hl_group = 'SpaceghostMenuKey' })
    elseif it.note then
      vim.api.nvim_buf_set_extmark(buf, ns, i - 1, 0, { end_col = #lines[i], hl_group = 'SpaceghostMenuHint' })
    end
  end
  local function close() if vim.api.nvim_win_is_valid(win) then vim.api.nvim_win_close(win, true) end end
  local function run(it) close(); vim.schedule(it.action) end
  for _, it in ipairs(items) do
    if it.key then vim.keymap.set('n', it.key, function() run(it) end, { buffer = buf, nowait = true }) end
  end
  vim.keymap.set('n', '<CR>', function()
    local it = items[vim.api.nvim_win_get_cursor(win)[1]]
    if it and it.action then run(it) end
  end, { buffer = buf, nowait = true })
  for _, k in ipairs({ 'q', '<Esc>', '<C-c>' }) do vim.keymap.set('n', k, close, { buffer = buf, nowait = true }) end
  vim.api.nvim_create_autocmd('WinLeave', { buffer = buf, once = true, callback = close })
end

function M.command_deck()
  local K = require('spaceghost.keys')
  M.menu('command deck', {
    { key = 'c', label = 'New tab shell', action = function() shell.open('tabnew') end },
    { key = 's', label = 'Split shell below', action = function() shell.open('belowright new') end },
    { key = 'v', label = 'Split shell right', action = function() shell.open('belowright vnew') end },
    { key = 'e', label = 'Edit a file…', action = K.edit_prompt },
    { key = 'a', label = 'Attach to a machine in a split…', action = K.attach_prompt },
    { key = 'z', label = 'Zoom / unzoom pane', action = K.zoom },
    { key = '=', label = 'Balance panes', action = function() vim.cmd('wincmd =') end },
    { key = 'x', label = 'Close pane', action = K.close_pane },
    { sep = true },
    { key = 'w', label = 'Tabs + panes', action = M.choose_window },
    { key = ',', label = 'Rename tab', action = M.rename_tab },
    { key = '`', label = 'Scratch terminal', action = function() shell.float(nil, { key = 'scratch', title = 'scratch terminal' }) end },
    { key = 'g', label = 'Git observatory', action = M.git_observatory },
    { key = '~', label = 'Process monitor', action = M.monitor },
    { sep = true },
    { key = 'n', label = 'Rebuild native helpers (nelua + zig cc)', action = M.rebuild_native },
    { key = 'r', label = 'Reload configuration', action = M.reload },
    { key = '?', label = 'Field guide', action = M.field_guide },
  })
end

function M.field_guide()
  local native = require('spaceghost.native')
  M.menu('flight manual', {
    { note = 'PREFIX: Ctrl-\\ or Ctrl-Space   /   prefix twice sends it through' },
    { sep = true },
    { note = 'Space      command deck     ?  F1   field guide' },
    { note = 'c          new tab shell    s / v   split below / right' },
    { note = 'h j k l    focus pane       H J K L resize pane' },
    { note = 'n / p      next/prev tab    1-9     jump to tab' },
    { note = 'Tab        last pane        w       tabs + panes' },
    { note = 'z / =      zoom / balance   x       close pane' },
    { note = '`          scratch shell    g       git observatory' },
    { note = '[          copy mode        ]       paste into shell' },
    { note = 'e          edit a file      ,       rename tab' },
    { note = 'a          attach machine   Ctrl-]  prefix to remote on/off' },
    { note = 'r          reload config    Ctrl-n  leave terminal mode' },
    { sep = true },
    { note = 'NOW selected   NEW unread   LIVE shell   EDIT file   EXIT dead' },
    { note = 'native: ' .. native.backend .. (native.error and (' (' .. native.error .. ')') or '') },
    { sep = true },
    { key = 'q', label = 'Close', action = function() end },
  })
end

function M.choose_window()
  local items = {}
  local keys = '123456789abcdfhijklmoprstuvy'
  local n = 0
  for ti, tab in ipairs(vim.api.nvim_list_tabpages()) do
    for _, win in ipairs(vim.api.nvim_tabpage_list_wins(tab)) do
      n = n + 1
      local key = keys:sub(n, n)
      if key == '' then break end
      local buf = vim.api.nvim_win_get_buf(win)
      items[#items + 1] = {
        key = key,
        label = string.format('tab %d  %s%s', ti, shell.label(buf), vim.b[buf].spaceghost_new and '  NEW' or ''),
        action = function()
          vim.api.nvim_set_current_tabpage(tab)
          vim.api.nvim_set_current_win(win)
        end,
      }
    end
  end
  M.menu('tabs + panes', items)
end

function M.rename_tab()
  vim.ui.input({ prompt = 'Tab name: ', default = vim.t.spaceghost_name or '' }, function(name)
    if name == nil then return end
    vim.t.spaceghost_name = name
    vim.cmd.redrawtabline()
  end)
end

function M.git_observatory()
  local cwd = shell.cwd(0)
  shell.float({ 'sh', '-c',
    'git --no-pager -c color.ui=always status --short --branch --untracked-files=no;'
    .. ' printf "\\nRECENT COMMITS\\n\\n"; git --no-pager -c color.ui=always log --oneline --decorate -12;'
    .. ' printf "\\nEnter to close"; read -r _' },
    { title = 'git observatory', cwd = cwd, width = 0.9, height = 0.8 })
end

function M.monitor()
  local cmd = vim.fn.executable('btop') == 1 and 'btop' or (vim.fn.executable('htop') == 1 and 'htop' or 'top')
  shell.float({ cmd }, { title = cmd, width = 0.9, height = 0.85 })
end

function M.rebuild_native()
  local script = vim.fn.expand('~/.bin/spaceghost-native')
  shell.float({ 'sh', '-c', vim.fn.shellescape(script) .. ' && printf "\\nbuilt. restart Neovim to load it. Enter to close" || printf "\\nbuild failed. Enter to close"; read -r _' },
    { title = 'native build', width = 0.8, height = 0.6 })
end

function M.reload()
  for name in pairs(package.loaded) do
    if name:match('^spaceghost') then package.loaded[name] = nil end
  end
  vim.cmd.source(vim.env.MYVIMRC)
  vim.notify('SPACEGHOST / systems reloaded')
end

return M
