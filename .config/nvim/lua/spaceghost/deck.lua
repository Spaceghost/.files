-- Command deck, field guide, popups. Floating menus with single-key actions.
local M = {}
local shell = require('spaceghost.shell')

-- items: { { key = 'c', label = 'New tab shell', action = fn }, { sep = true }, { note = '...' } }
function M.menu(title, items)
  vim.cmd.stopinsert()
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
    { key = 'i', label = 'Codex / Agentic…', action = function() require('spaceghost.agent').menu() end },
    { key = 'z', label = 'Zoom / unzoom pane', action = K.zoom },
    { key = '=', label = 'Balance panes', action = function() vim.cmd('wincmd =') end },
    { key = 'd', label = 'Redraw pane', action = shell.redraw },
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
    { note = 'F2         find any pane    /       search tab, host or directory' },
    { note = 'Ctrl-\\ then h/j/k/l: panes   Alt-[ / Alt-]: previous/next tab' },
    { note = 'Alt-1..9   jump to tab      Ctrl-PgUp/PgDn previous / next tab' },
    { note = 'Alt-o      previous pane across tabs    F4 command deck' },
    { note = 'Alt-arrows pass through to terminal programs' },
    { note = 'F4 then d: redraw pane    F4 then x: close pane' },
    { note = 'F2 then x: remove selected duplicate view (keep its shell)' },
    { sep = true },
    { note = 'Space      command deck     ?  F1   field guide' },
    { note = 'c          new tab shell    s / v   split below / right' },
    { note = 'h j k l    focus pane       H J K L resize pane' },
    { note = 'n / p      next/prev tab    1-9     jump to tab' },
    { note = 'Tab        previous pane across tabs    w  find any pane' },
    { note = 'z / =      zoom / balance   x       close pane' },
    { note = 'd          redraw pane (duplicate views share one shell)' },
    { note = '`          scratch shell    g       git observatory' },
    { note = '[          copy mode        ]       paste into shell' },
    { note = 'e          edit a file      ,       rename tab' },
    { note = 'a          attach machine   Ctrl-]  all navigation local/remote' },
    { note = 'i          native Codex      I       add file/selection to Codex' },
    { note = 'F4 i       Codex sessions, restore and layout controls' },
    { note = 'Choose a host in F2 to enter its tabs and panes' },
    { note = 'r          reload config    Ctrl-\\ Ctrl-n  leave terminal mode' },
    { sep = true },
    { note = 'NOW selected   NEW unread   LIVE shell   EDIT file   EXIT dead' },
    { note = 'native: ' .. native.backend .. (native.error and (' (' .. native.error .. ')') or '') },
    { sep = true },
    { key = 'q', label = 'Close', action = function() end },
  })
end

function M.choose_window()
  vim.cmd.stopinsert()
  local origin = vim.api.nvim_get_current_win()
  local entries, lines, selected = {}, {}, 1
  local function clean(value) return (value:gsub('[%c]', ' ')) end
  for ti, tab in ipairs(vim.api.nvim_list_tabpages()) do
    local pane = 0
    for _, target in ipairs(vim.api.nvim_tabpage_list_wins(tab)) do
      if vim.api.nvim_win_get_config(target).relative == '' then
        pane = pane + 1
        local buf = vim.api.nvim_win_get_buf(target)
        local host = vim.b[buf].spaceghost_attach
        local kind = host and 'remote' or (shell.is_shell(buf) and 'shell' or 'file')
        local title = vim.t[tab].spaceghost_name or ''
        if title ~= '' then title = ' / ' .. title end
        entries[#entries + 1] = target
        local views = #vim.fn.win_findbuf(buf)
        lines[#lines + 1] = clean(string.format('%s tab %d%s | pane %d | %s | %s | %s%s%s',
          target == origin and '>' or ' ', ti, title, pane, kind, shell.label(buf),
          vim.fn.fnamemodify(shell.cwd(buf), ':~'), views > 1 and ('  SHARED ' .. views) or '',
          vim.b[buf].spaceghost_new and '  NEW' or ''))
        if target == origin then selected = #entries end
      end
    end
  end
  if #entries == 0 then return end
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].bufhidden = 'wipe'
  local width = math.max(1, math.min(110, vim.o.columns - 4))
  local height = math.max(1, math.min(#entries, vim.o.lines - vim.o.cmdheight - 4))
  local win = vim.api.nvim_open_win(buf, true, {
    relative = 'editor', width = width, height = height,
    row = math.max(0, math.floor((vim.o.lines - height - 2) / 2)),
    col = math.max(0, math.floor((vim.o.columns - width) / 2)),
    style = 'minimal', border = 'rounded', title = ' Tabs / panes / hosts ',
    footer = ' / search  j/k move  Enter focus/host  x remove duplicate  Esc cancel ',
  })
  vim.wo[win].cursorline = true
  vim.wo[win].wrap = false
  vim.api.nvim_win_set_cursor(win, { selected, 0 })
  vim.cmd.stopinsert()
  local function close()
    if vim.api.nvim_win_is_valid(win) then vim.api.nvim_win_close(win, true) end
  end
  local function select_pane()
    local target = entries[vim.api.nvim_win_get_cursor(win)[1]]
    close()
    if vim.api.nvim_win_is_valid(target) then
      vim.api.nvim_set_current_win(target)
      shell.navigate_remote()
    end
  end
  for _, key in ipairs({ '<CR>', '<Space>' }) do
    vim.keymap.set('n', key, select_pane, { buffer = buf, nowait = true })
  end
  vim.keymap.set('n', 'x', function()
    local target = entries[vim.api.nvim_win_get_cursor(win)[1]]
    if not vim.api.nvim_win_is_valid(target) then return end
    local target_buf = vim.api.nvim_win_get_buf(target)
    if #vim.fn.win_findbuf(target_buf) < 2 then
      vim.notify('Only one view of this pane is open.')
      return
    end
    close()
    vim.api.nvim_win_close(target, false)
  end, { buffer = buf, nowait = true, desc = 'Remove a duplicate view, keeping its terminal running' })
  for _, key in ipairs({ '<Esc>', 'q', '<C-c>', '<F2>' }) do
    vim.keymap.set('n', key, close, { buffer = buf, nowait = true })
  end
  vim.keymap.set('n', '<Tab>', 'j', { buffer = buf })
  vim.keymap.set('n', '<S-Tab>', 'k', { buffer = buf })
  vim.api.nvim_create_autocmd('WinLeave', { buffer = buf, once = true, callback = close })
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
