-- Tabline (window list), global statusline (HUD), terminal title.
local M = {}
local shell = require('spaceghost.shell')
local native = require('spaceghost.native')
local detached_tabs = rawget(_G, 'spaceghost_detached_tabs') or {}
_G.spaceghost_detached_tabs = detached_tabs

local function hl(group, text) return '%#' .. group .. '#' .. text end
local function literal(text) return tostring(text):gsub('[%c]', ' '):gsub('%%', '%%%%') end

-- ── Tabline: one entry per tab, tmux window-list style ────────────────────────
local function tab_label(tab)
  local name = vim.t[tab].spaceghost_name
  if name and name ~= '' then return name end
  local win = vim.api.nvim_tabpage_get_win(tab)
  return shell.label(vim.api.nvim_win_get_buf(win))
end

local function tab_state(tab)
  local wins = vim.api.nvim_tabpage_list_wins(tab)
  local has_new, has_term, dead = false, false, false
  for _, w in ipairs(wins) do
    local b = vim.api.nvim_win_get_buf(w)
    if vim.b[b].spaceghost_new then has_new = true end
    if vim.bo[b].buftype == 'terminal' then
      has_term = true
      local ok, chan = pcall(function() return vim.bo[b].channel end)
      if ok and chan and vim.fn.jobwait({ chan }, 0)[1] ~= -1 then dead = true end
    end
  end
  return { new = has_new, term = has_term, dead = dead, panes = #wins }
end

function M.tab_click(index, clicks, button)
  local tab = vim.api.nvim_list_tabpages()[index]
  if not tab then return end
  if button == 'm' then
    vim.cmd(index .. 'tabclose')
  elseif button == 'r' then
    M.tab_menu(tab)
  elseif button == 'l' then
    vim.api.nvim_set_current_tabpage(tab)
    if clicks >= 2 then shell.open('tabnew') end
  end
end

local function tab_buffers(tab)
  local buffers, seen = {}, {}
  for _, win in ipairs(vim.api.nvim_tabpage_list_wins(tab)) do
    if vim.api.nvim_win_get_config(win).relative == '' then
      local buf = vim.api.nvim_win_get_buf(win)
      if not seen[buf] then buffers[#buffers + 1], seen[buf] = buf, true end
    end
  end
  return buffers
end

function M.detach_tab(tab)
  if not vim.api.nvim_tabpage_is_valid(tab) then return end
  local entry = { label = tab_label(tab), buffers = tab_buffers(tab) }
  if #vim.api.nvim_list_tabpages() == 1 then shell.open('$tabnew') end
  vim.cmd(vim.api.nvim_tabpage_get_number(tab) .. 'tabclose')
  detached_tabs[#detached_tabs + 1] = entry
end

function M.close_tab(tab)
  if not vim.api.nvim_tabpage_is_valid(tab) then return end
  local buffers = tab_buffers(tab)
  if #vim.api.nvim_list_tabpages() == 1 then shell.open('$tabnew') end
  vim.cmd(vim.api.nvim_tabpage_get_number(tab) .. 'tabclose')
  for _, buf in ipairs(buffers) do
    if vim.api.nvim_buf_is_valid(buf) and vim.bo[buf].buftype == 'terminal'
        and #vim.fn.win_findbuf(buf) == 0 then
      -- Closing a tab must not make the root shell's TermClose quit the session.
      vim.b[buf].spaceghost_shell_root = false
      vim.api.nvim_buf_delete(buf, { force = true })
    end
  end
end

function M.reopen_detached()
  local available = {}
  for _, entry in ipairs(detached_tabs) do
    for _, buf in ipairs(entry.buffers) do
      if vim.api.nvim_buf_is_valid(buf) then
        available[#available + 1] = entry
        break
      end
    end
  end
  if #available == 0 then vim.notify('No detached tabs to reopen'); return end
  vim.ui.select(available, {
    prompt = 'Reopen detached tab:',
    format_item = function(entry) return entry.label end,
  }, function(entry)
    if not entry then return end
    for i, candidate in ipairs(detached_tabs) do
      if candidate == entry then table.remove(detached_tabs, i); break end
    end
    local first = true
    for _, buf in ipairs(entry.buffers) do
      if vim.api.nvim_buf_is_valid(buf) then
        if first then vim.cmd.tabnew(); first = false else vim.cmd('belowright vnew') end
        vim.api.nvim_win_set_buf(0, buf)
      end
    end
  end)
end

function M.tab_menu(tab)
  local deck = require('spaceghost.deck')
  deck.menu('tab / ' .. tab_label(tab), {
    { key = 'd', label = 'Detach tab / keep shells', action = function() M.detach_tab(tab) end },
    { key = 'x', label = 'Close tab / stop shells', action = function() M.close_tab(tab) end },
    { sep = true },
    { key = 'r', label = 'Reopen detached tab…', action = M.reopen_detached },
  }, { row = 1, col = math.max(0, vim.fn.getmousepos().screencol - 1), mouse = true })
end

local plus_hold

local function stop_plus_hold()
  if plus_hold and plus_hold.timer then
    plus_hold.timer:stop()
    plus_hold.timer:close()
  end
  plus_hold = nil
end

local function plus_menu()
  local deck = require('spaceghost.deck')
  local keys = require('spaceghost.keys')
  local items = {
    { key = 'c', label = 'Local shell tab', action = function() shell.open('$tabnew') end },
    { sep = true },
  }
  local current_host = vim.fn.hostname():lower():match('^[^.]+')
  for _, host in ipairs({ 'bak', 'fedora', 'alienware' }) do
    if host ~= current_host then
      items[#items + 1] = {
        key = host:sub(1, 1), label = host,
        action = function() shell.attach(host, 'tabnew') end,
      }
    end
  end
  vim.list_extend(items, {
    { key = 'o', label = 'Other host…', action = function() keys.attach_prompt('tabnew') end },
    { sep = true },
    { key = 'r', label = 'Reopen detached tab…', action = M.reopen_detached },
    { key = 'v', label = 'Split shell right', action = function() shell.open('belowright vnew') end },
  })
  deck.menu('new tab', items, { row = 1, col = M.plus_col or 0, mouse = true })
end

function M.plus_click(_, _, button)
  if button == 'r' then
    stop_plus_hold()
    plus_menu()
  elseif button == 'l' then
    stop_plus_hold()
    local timer = (vim.uv or vim.loop).new_timer()
    local hold = { timer = timer, opened = false }
    plus_hold = hold
    timer:start(450, 0, vim.schedule_wrap(function()
      if plus_hold ~= hold then return end
      hold.opened = true
      timer:stop()
      timer:close()
      hold.timer = nil
      plus_menu()
    end))
  end
end

function M.plus_release()
  if not plus_hold then return end
  local open_tab = not plus_hold.opened
  stop_plus_hold()
  if open_tab then vim.schedule(function() shell.open('$tabnew') end) end
end

function M.empty_click(_, clicks, button)
  if button == 'l' and clicks >= 2 then shell.open('$tabnew') end
end

function M.tabline()
  local parts = {}
  local width = vim.o.columns
  local badge = width >= 160 and ' S P A C E G H O S T ' or (width >= 100 and ' SPACEGHOST ' or ' SG ')
  parts[#parts + 1] = hl('SpaceghostBadge', badge)
  parts[#parts + 1] = hl('SpaceghostSurface', ' ' .. literal(vim.fn.fnamemodify(vim.fn.getcwd(-1, -1), ':t')) .. ' ')
  parts[#parts + 1] = hl('TabLineFill', ' ')
  local current = vim.api.nvim_get_current_tabpage()
  local maxlen = width >= 180 and 26 or 14
  local tabs = vim.api.nvim_list_tabpages()
  for i, tab in ipairs(tabs) do
    local label = tab_label(tab)
    if vim.fn.strchars(label) > maxlen then label = vim.fn.strcharpart(label, 0, maxlen - 1) .. '…' end
    label = literal(label)
    local st = tab_state(tab)
    if tab == current then
      local extra = st.panes > 1 and (' +' .. st.panes) or ''
      parts[#parts + 1] = '%' .. i .. '@v:lua.Spaceghost.ui.tab_click@'
        .. hl('SpaceghostTabSel', ' ' .. i .. ' / ' .. label .. '  NOW' .. extra .. ' ') .. '%X'
    else
      local group = st.new and 'SpaceghostTabNew' or 'SpaceghostTab'
      local state = st.dead and hl('SpaceghostStateExit', 'EXIT')
        or (st.new and hl('SpaceghostStateNew', 'NEW') or hl('SpaceghostStateLive', st.term and 'LIVE' or 'EDIT'))
      parts[#parts + 1] = '%' .. i .. '@v:lua.Spaceghost.ui.tab_click@'
        .. hl(group, ' ' .. i .. ' ' .. label .. ' ') .. state .. hl(group, ' ') .. '%X'
    end
    parts[#parts + 1] = hl('TabLineFill', ' ')
  end
  M.plus_col = vim.api.nvim_eval_statusline(table.concat(parts), { use_tabline = true }).width
  parts[#parts + 1] = '%@v:lua.Spaceghost.ui.plus_click@' .. hl('SpaceghostTab', '  ') .. '%X'
  parts[#parts + 1] = '%@v:lua.Spaceghost.ui.empty_click@%=' .. hl('TabLineFill', ' ') .. '%X'
    .. hl('SpaceghostMuted', '')
  if width >= 150 then parts[#parts + 1] = hl('SpaceghostMuted', vim.fn.hostname() .. ' / ') end
  parts[#parts + 1] = hl('TabLine', os.date(width >= 180 and '%H:%M %a %d %b ' or '%H:%M '))
  return table.concat(parts)
end

-- ── Statusline: mode, cwd, branch, telemetry ──────────────────────────────────
local modes = {
  n = { 'NORMAL', 'SpaceghostModeNormal' }, no = { 'OP', 'SpaceghostModeNormal' },
  i = { 'INSERT', 'SpaceghostModeInsert' }, t = { 'SHELL', 'SpaceghostModeTerminal' },
  v = { 'VISUAL', 'SpaceghostModeVisual' }, V = { 'V-LINE', 'SpaceghostModeVisual' },
  ['\22'] = { 'V-BLOCK', 'SpaceghostModeVisual' }, s = { 'SELECT', 'SpaceghostModeVisual' },
  R = { 'REPLACE', 'SpaceghostModeReplace' }, c = { 'COMMAND', 'SpaceghostModeCommand' },
  r = { 'PROMPT', 'SpaceghostModeCommand' }, ['!'] = { 'SHELL', 'SpaceghostModeTerminal' },
  nt = { 'TERM', 'SpaceghostModeNormal' },
}

local branch_cache = {}
local function git_branch(cwd)
  local entry = branch_cache[cwd]
  local now = (vim.uv or vim.loop).now()
  if entry and now - entry.at < 5000 then return entry.value end
  if entry and entry.pending then return entry.value end
  branch_cache[cwd] = { at = now, value = entry and entry.value or '', pending = true }
  vim.system({ 'git', '-C', cwd, 'symbolic-ref', '--quiet', '--short', 'HEAD' }, { text = true }, function(res)
    local value = ''
    if res.code == 0 then
      value = (res.stdout or ''):gsub('%s+$', ''):gsub('[^%w%._/:-]', '?'):sub(1, 24)
    end
    branch_cache[cwd] = { at = (vim.uv or vim.loop).now(), value = value, pending = false }
    vim.schedule(function()
      if #vim.api.nvim_list_uis() > 0 then pcall(vim.cmd.redrawstatus) end
    end)
  end)
  return branch_cache[cwd].value
end

local telemetry_cache = { at = 0 }
local function telemetry()
  local now = (vim.uv or vim.loop).now()
  if now - telemetry_cache.at > 5000 then
    telemetry_cache = { at = now, value = native.telemetry() }
  end
  return telemetry_cache.value
end

function M.statusline()
  local buf = vim.api.nvim_get_current_buf()
  local mode = vim.api.nvim_get_mode().mode
  local copying = vim.bo[buf].buftype == 'terminal' and (mode == 'n' or mode == 'nt')
  local m = copying and { 'COPY', 'SpaceghostModeVisual' }
    or modes[mode] or modes[mode:sub(1, 1)] or { '?', 'SpaceghostModeNormal' }
  local width = vim.o.columns
  local parts = { hl(m[2], ' ' .. m[1] .. ' ') }
  local cwd = shell.cwd(buf)
  local short = width >= 140 and native.short_path(cwd) or vim.fn.fnamemodify(cwd, ':t')
  local what
  if vim.bo[buf].buftype == 'terminal' then
    local title = (vim.b[buf].term_title or ''):gsub('^[%w%.%-_]+@[%w%.%-_]+:%s*', '')
    if title == '' or title:match('^[~/]') then title = 'shell' end
    what = hl('SpaceghostStatusAccent', ' ' .. literal(title:sub(1, 40)))
  else
    local name = vim.api.nvim_buf_get_name(buf)
    name = name == '' and '[scratch]' or vim.fn.fnamemodify(name, ':~:.')
    what = hl('SpaceghostStatusAccent', ' ' .. literal(name)) .. (vim.bo[buf].modified and hl('SpaceghostStatusWarn', ' +') or '')
      .. (vim.bo[buf].readonly and hl('SpaceghostStatusAlert', ' RO') or '')
  end
  parts[#parts + 1] = what
  if vim.b[buf].spaceghost_remote_keys then
    parts[#parts + 1] = hl('StatusLine', ' ') .. hl('SpaceghostModeVisual', ' REMOTE @' .. vim.b[buf].spaceghost_attach .. ' / ^] local ')
  end
  parts[#parts + 1] = hl('StatusLine', ' / ') .. hl('SpaceghostStatusCwd', literal(short))
  local branch = git_branch(cwd)
  if branch ~= '' then parts[#parts + 1] = hl('StatusLine', ' ') .. hl('SpaceghostStatusBranch', ' ' .. branch) end
  parts[#parts + 1] = '%='
  local right = {}
  local worker_ui = package.loaded['spaceghost.worker_ui']
  if worker_ui then right[#right + 1] = worker_ui.statusline() .. hl('StatusLine', '') end
  local t = width >= 120 and telemetry() or nil
  if t then
    if t.load1 >= 0 then right[#right + 1] = 'LOAD ' .. hl('SpaceghostStatusCwd', string.format('%.2f', t.load1)) .. hl('StatusLine', '') end
    if t.mem_total_kb > 0 and t.mem_avail_kb >= 0 then
      local pct = math.floor((1 - t.mem_avail_kb / t.mem_total_kb) * 100 + 0.5)
      right[#right + 1] = 'MEM ' .. hl(pct >= 90 and 'SpaceghostStatusAlert' or 'SpaceghostStatusCwd', pct .. '%%') .. hl('StatusLine', '')
    end
    if t.battery_pct >= 0 then
      local g = t.battery_pct <= 15 and 'SpaceghostStatusAlert' or 'SpaceghostStatusCwd'
      right[#right + 1] = 'BAT ' .. hl(g, t.battery_pct .. '%%' .. (t.battery_charging and '+' or '')) .. hl('StatusLine', '')
    end
  end
  if vim.bo[buf].buftype ~= 'terminal' then
    right[#right + 1] = (vim.bo[buf].filetype ~= '' and vim.bo[buf].filetype or 'text')
    right[#right + 1] = hl('SpaceghostStatusCwd', '%l') .. hl('StatusLine', ':%c  %P')
  else
    right[#right + 1] = 'TAB ' .. hl('SpaceghostStatusCwd', vim.fn.tabpagenr() .. '/' .. vim.fn.tabpagenr('$')) .. hl('StatusLine', '')
    right[#right + 1] = 'PANE ' .. hl('SpaceghostStatusCwd', vim.fn.winnr() .. '/' .. vim.fn.winnr('$')) .. hl('StatusLine', '')
  end
  if shell.is_server then right[#right + 1] = hl('SpaceghostStatusBranch', 'SRV') .. hl('StatusLine', '') end
  if copying then
    right[#right + 1] = hl('SpaceghostStatusBranch', width >= 110 and '^\\ u prompt / v select / i shell' or 'i shell')
      .. hl('StatusLine', ' ')
  else
    right[#right + 1] = hl('SpaceghostStatusBranch', 'F2 panes') .. hl('StatusLine', width >= 110 and ' / F4 menu ' or ' ')
  end
  parts[#parts + 1] = hl('StatusLine', table.concat(right, '  '))
  return table.concat(parts)
end

function M.title()
  local tab = vim.api.nvim_get_current_tabpage()
  return tab_label(tab) .. ' / Spaceghost'
end

function M.setup()
  stop_plus_hold()
  local ns = vim.api.nvim_create_namespace('spaceghost-plus-hold')
  local release = vim.keycode('<LeftRelease>')
  vim.on_key(function(key)
    if key ~= release or not plus_hold then return end
    M.plus_release()
  end, ns)
  -- Commands temporarily overlay the last row; shells keep it the rest of the
  -- time. Leave columns/lines and PTY resizing to Neovim's smallest attached UI.
  vim.o.cmdheight = 0
  vim.o.showtabline = 2
  vim.o.laststatus = 3
  vim.o.showmode = false
  vim.o.ruler = false
  vim.o.title = true
  vim.o.titlestring = '%{v:lua.Spaceghost.ui.title()}'
  vim.o.tabline = '%!v:lua.Spaceghost.ui.tabline()'
  vim.o.statusline = '%!v:lua.Spaceghost.ui.statusline()'
  vim.o.fillchars = 'horiz:─,horizup:┴,horizdown:┬,vert:│,vertleft:┤,vertright:├,verthoriz:┼,eob: ,fold: '
  -- Clock and telemetry refresh.
  local old_timer = rawget(_G, 'spaceghost_hud_timer')
  if old_timer and not old_timer:is_closing() then old_timer:stop(); old_timer:close() end
  local timer = (vim.uv or vim.loop).new_timer()
  _G.spaceghost_hud_timer = timer
  timer:start(15000, 15000, vim.schedule_wrap(function()
    if #vim.api.nvim_list_uis() == 0 then return end
    pcall(vim.cmd.redrawtabline); pcall(vim.cmd.redrawstatus)
  end))
  local group = vim.api.nvim_create_augroup('SpaceghostHUD', { clear = true })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    if not timer:is_closing() then timer:stop(); timer:close() end
  end })
end

return M
