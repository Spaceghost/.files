-- Tabline (window list), global statusline (HUD), terminal title.
local M = {}
local shell = require('spaceghost.shell')
local native = require('spaceghost.native')

local function hl(group, text) return '%#' .. group .. '#' .. text end

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

function M.tabline()
  local parts = {}
  local width = vim.o.columns
  local badge = width >= 160 and ' S P A C E G H O S T ' or (width >= 100 and ' SPACEGHOST ' or ' SG ')
  parts[#parts + 1] = hl('SpaceghostBadge', badge)
  parts[#parts + 1] = hl('SpaceghostSurface', ' ' .. vim.fn.fnamemodify(vim.fn.getcwd(-1, -1), ':t') .. ' ')
  parts[#parts + 1] = hl('TabLineFill', ' ')
  local current = vim.api.nvim_get_current_tabpage()
  local maxlen = width >= 180 and 26 or 14
  for i, tab in ipairs(vim.api.nvim_list_tabpages()) do
    local label = tab_label(tab)
    if #label > maxlen then label = label:sub(1, maxlen - 1) .. '…' end
    local st = tab_state(tab)
    if tab == current then
      local extra = st.panes > 1 and (' +' .. st.panes) or ''
      parts[#parts + 1] = '%' .. i .. 'T' .. hl('SpaceghostTabSel', ' ' .. i .. ' / ' .. label .. '  NOW' .. extra .. ' ') .. '%T'
    else
      local group = st.new and 'SpaceghostTabNew' or 'SpaceghostTab'
      local state = st.dead and hl('SpaceghostStateExit', 'EXIT')
        or (st.new and hl('SpaceghostStateNew', 'NEW') or hl('SpaceghostStateLive', st.term and 'LIVE' or 'EDIT'))
      parts[#parts + 1] = '%' .. i .. 'T' .. hl(group, ' ' .. i .. ' ' .. label .. ' ') .. state .. hl(group, ' ') .. '%T'
    end
    parts[#parts + 1] = hl('TabLineFill', ' ')
  end
  parts[#parts + 1] = '%=' .. hl('SpaceghostMuted', '')
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
    vim.schedule(function() pcall(vim.cmd.redrawstatus) end)
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
  local m = modes[vim.api.nvim_get_mode().mode] or modes[vim.api.nvim_get_mode().mode:sub(1, 1)] or { '?', 'SpaceghostModeNormal' }
  local width = vim.o.columns
  local parts = { hl(m[2], ' ' .. m[1] .. ' ') }
  local cwd = shell.cwd(buf)
  local short = width >= 140 and native.short_path(cwd) or vim.fn.fnamemodify(cwd, ':t')
  local what
  if vim.bo[buf].buftype == 'terminal' then
    local title = (vim.b[buf].term_title or ''):gsub('^[%w%.%-_]+@[%w%.%-_]+:%s*', '')
    if title == '' or title:match('^[~/]') then title = 'shell' end
    what = hl('SpaceghostStatusAccent', ' ' .. title:sub(1, 40))
  else
    local name = vim.api.nvim_buf_get_name(buf)
    name = name == '' and '[scratch]' or vim.fn.fnamemodify(name, ':~:.')
    what = hl('SpaceghostStatusAccent', ' ' .. name) .. (vim.bo[buf].modified and hl('SpaceghostStatusWarn', ' +') or '')
      .. (vim.bo[buf].readonly and hl('SpaceghostStatusAlert', ' RO') or '')
  end
  parts[#parts + 1] = what
  if vim.b[buf].spaceghost_remote_keys then
    parts[#parts + 1] = hl('StatusLine', ' ') .. hl('SpaceghostModeVisual', ' REMOTE KEYS / ^] back ')
  end
  parts[#parts + 1] = hl('StatusLine', ' / ') .. hl('SpaceghostStatusCwd', short)
  local branch = git_branch(cwd)
  if branch ~= '' then parts[#parts + 1] = hl('StatusLine', ' ') .. hl('SpaceghostStatusBranch', ' ' .. branch) end
  parts[#parts + 1] = '%='
  local right = {}
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
    right[#right + 1] = 'PANE ' .. hl('SpaceghostStatusCwd', vim.fn.winnr() .. '/' .. vim.fn.winnr('$')) .. hl('StatusLine', '')
  end
  if shell.is_server then right[#right + 1] = hl('SpaceghostStatusBranch', 'SRV') .. hl('StatusLine', '') end
  right[#right + 1] = hl('SpaceghostStatusBranch', '^\\ SPACE') .. hl('StatusLine', width >= 110 and ' / deck ' or ' ')
  parts[#parts + 1] = hl('StatusLine', table.concat(right, '  '))
  return table.concat(parts)
end

function M.title()
  local tab = vim.api.nvim_get_current_tabpage()
  return tab_label(tab) .. ' / Spaceghost'
end

function M.setup()
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
  local timer = (vim.uv or vim.loop).new_timer()
  timer:start(15000, 15000, vim.schedule_wrap(function()
    pcall(vim.cmd.redrawtabline); pcall(vim.cmd.redrawstatus)
  end))
end

return M
