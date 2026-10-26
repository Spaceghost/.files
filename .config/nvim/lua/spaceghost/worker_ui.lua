-- Native worker cockpit. Engine ticks drive visible motion; no UI timer is needed.
local M = {}
local api = vim.api
local workers = require('spaceghost.workers')
local ns = api.nvim_create_namespace('spaceghost-workers')
local S = rawget(_G, '__spaceghost_worker_ui') or { selected = nil, offset = 1, detail = false }
_G.__spaceghost_worker_ui = S
local busy = { starting = true, thinking = true, working = true, stopping = true }
local frames = { '⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏' }
local function clean(v) return tostring(v or ''):gsub('[%c]', ' ') end
local function fit(v, width)
  v = clean(v)
  if width <= 0 then return '' end
  if vim.fn.strdisplaywidth(v) > width then
    local out = ''
    for ch in v:gmatch('[%z\1-\127\194-\244][\128-\191]*') do
      if vim.fn.strdisplaywidth(out .. ch) > width - 1 then break end
      out = out .. ch
    end
    return out .. '…'
  end
  return v
end
local function pad(v, width) v = fit(v, width); return v .. string.rep(' ', math.max(0, width - vim.fn.strdisplaywidth(v))) end
local function phase() return vim.g.spaceghost_worker_motion == false and 0 or math.floor((vim.uv or vim.loop).now() / 120) end
local function glyph(r)
  if busy[r.status] then return frames[phase() % #frames + 1] end
  return ({ waiting = '◆', done = '✓', failed = '!', ready = '○' })[r.status] or '○'
end
local function tone(r) return r.status == 'failed' and 'WorkerFailed' or r.status == 'waiting' and 'WorkerWaiting' or r.status == 'done' and 'WorkerDone' or 'WorkerAccent' end
local function label(r) return r.status == 'waiting' and 'NEEDS YOU' or clean(r.status or 'unknown'):upper() end
local function plan(r)
  local total, done = #(r.plan or {}), 0
  for _, p in ipairs(r.plan or {}) do if p.status == 'completed' or p.status == 'complete' or p.status == 'done' then done = done + 1 end end
  return done, total
end
local function bar(used, total, width)
  if not total or total <= 0 or not used then return 'unavailable' end
  local filled = math.max(0, math.min(width, math.floor(width * used / total)))
  return string.rep('━', filled) .. string.rep('┄', width - filled)
end
local function sweep(width)
  local pos = phase() % math.max(1, width - 2)
  return string.rep('─', pos) .. '━━' .. string.rep('─', math.max(0, width - pos - 2))
end
local function elapsed(r)
  local sec = math.max(0, (r.finished_at or os.time()) - (r.started_at or os.time()))
  return string.format('%02d:%02d', math.floor(sec / 60), sec % 60)
end
local function visible() return S.win and api.nvim_win_is_valid(S.win) and api.nvim_win_get_tabpage(S.win) == api.nvim_get_current_tabpage() end
local function records()
  local list = workers.list()
  local index = 1
  for i, r in ipairs(list) do if r.id == S.selected then index = i; break end end
  if not S.selected or not workers.get(S.selected) then S.selected = list[index] and list[index].id end
  return list, index
end
local function detail(r, width)
  local out = {}
  local function add(text, group) out[#out + 1] = { fit(text, width), group or 'WorkerText' } end
  if not r then add('YOUR NEXT WORKER STARTS HERE', 'WorkerTitle'); add(''); add('n  Create an independent Codex session'); add('N  Choose another workspace'); add(''); add('Each session keeps its own tab and inbox.'); return out end
  add('SELECTED / ' .. r.name, 'WorkerTitle')
  add(glyph(r) .. ' ' .. label(r) .. '  ·  ' .. elapsed(r), tone(r))
  add('Workspace  ' .. clean(r.cwd), 'WorkerMuted')
  add('Identity   ' .. r.id, 'WorkerMuted')
  add('Model      ' .. (r.model or 'unavailable'), 'WorkerMuted')
  add('Bridge     ' .. (r.bridge and 'available' or 'unavailable'), 'WorkerMuted')
  add('')
  local done, total = plan(r)
  add('PLAN  ' .. (total > 0 and done .. '/' .. total .. ' complete' or 'unavailable'), 'WorkerTitle')
  add(bar(total > 0 and done or nil, total, math.min(30, width)), 'WorkerProgress')
  for _, p in ipairs(r.plan or {}) do
    if #out >= 13 then break end
    add('  ' .. ((p.status == 'completed' or p.status == 'done') and '✓ ' or '· ') .. clean(p.content or p.text or p.title), 'WorkerMuted')
  end
  local u = r.usage or {}
  add('CONTEXT  ' .. (u.used and u.size and u.size > 0 and math.floor(u.used / u.size * 100) .. '% used' or 'unavailable'), 'WorkerTitle')
  add(bar(u.used, u.size, math.min(30, width)), 'WorkerProgress')
  local files, tools = 0, 0
  for _ in pairs(r.changed_files or {}) do files = files + 1 end
  for _ in pairs(r.tools or {}) do tools = tools + 1 end
  add(files .. ' changed files  ·  ' .. tools .. ' tools  ·  ' .. #(r.queue or {}) .. ' queued', 'WorkerMuted')
  add('')
  add('ACTIVITY / ' .. clean(r.activity or 'Waiting for session events'), 'WorkerTitle')
  local events = r.events or {}
  for i = math.max(1, #events - 3), #events do
    local e = events[i]; add(os.date('%H:%M', e.at or os.time()) .. '  ' .. clean(e.text), 'WorkerMuted')
  end
  if r.error then add('ERROR  ' .. clean(r.error), 'WorkerFailed') end
  add('INBOX / ' .. (r.unread or 0) .. ' unread', 'WorkerTitle')
  local inbox = r.inbox or {}
  for i = math.max(1, #inbox - 2), #inbox do
    local m = inbox[i]
    local sender = m.from and workers.get(m.from)
    add(clean(m.from_name or (sender and sender.name) or m.from or m.sender or 'peer') .. ': ' .. clean(m.text or m.message) .. ' [' .. clean(m.status or 'received') .. ']', 'WorkerMuted')
  end
  if #inbox == 0 then add('No peer messages', 'WorkerMuted') end
  add('DELEGATED / interact through parent', 'WorkerTitle')
  local count = 0
  for _, child in pairs(r.children or {}) do
    if count >= 4 then break end
    add(glyph(child) .. ' ' .. clean(child.name or child.id or 'child') .. '  ' .. clean(child.status or child.activity), 'WorkerMuted'); count = count + 1
  end
  if count == 0 then add('No reported child activity', 'WorkerMuted') end
  return out
end
function M.render()
  if not visible() then return end
  local w, h = api.nvim_win_get_width(S.win), api.nvim_win_get_height(S.win)
  local wide = w >= 100
  local list, index = records()
  local summary = workers.summary()
  local header = ' SPACEGHOST / CODEX WORKERS'
  local counts = string.format('%d active  ·  %d need you  ·  %d unread', summary.running or 0, (summary.waiting or 0) + (summary.failed or 0), summary.unread or 0)
  local lines, marks = {}, {}
  local function row(left, lg, right, rg, split)
    local text = fit(left, split or w)
    if split then text = pad(text, split) .. ' │ ' .. fit(right or '', w - split - 3) end
    lines[#lines + 1] = text
    marks[#marks + 1] = { row = #lines - 1, col = 0, finish = split and #pad(fit(left, split), split) or #text, group = lg or 'WorkerText' }
    if split then marks[#marks + 1] = { row = #lines - 1, col = #pad(fit(left, split), split) + #' │ ', finish = #text, group = rg or 'WorkerText' } end
  end
  row(header, 'WorkerTitle'); row(' ' .. counts, (summary.waiting or 0) + (summary.failed or 0) > 0 and 'WorkerWaiting' or 'WorkerMuted')
  row(string.rep('─', w), 'WorkerBorder')
  local body = math.max(1, h - 6)
  local lw = wide and math.min(45, math.floor(w * .42)) or w
  local slots = math.max(1, math.floor(body / 4))
  if index < S.offset then S.offset = index end
  if index >= S.offset + slots then S.offset = index - slots + 1 end
  S.offset = math.max(1, math.min(S.offset, math.max(1, #list - slots + 1)))
  local left = {}
  local function add(text, group) left[#left + 1] = { fit(text, lw), group } end
  for i = S.offset, math.min(#list, S.offset + slots - 1) do
    local r = list[i]; local selected = r.id == S.selected
    add((selected and '▎ ' or '  ') .. glyph(r) .. ' ' .. label(r) .. ' / ' .. clean(r.name), selected and 'WorkerSelected' or tone(r))
    local done, total = plan(r)
    add('  ' .. (total > 0 and bar(done, total, 12) .. '  ' .. done .. '/' .. total .. ' plan' or busy[r.status] and sweep(math.min(20, lw - 4)) .. '  active' or 'Plan unavailable'), 'WorkerProgress')
    add('  ' .. elapsed(r) .. ' · ' .. clean(r.activity or r.cwd) .. ((r.unread or 0) > 0 and ' · inbox ' .. r.unread or ''), 'WorkerMuted')
    add('', 'WorkerText')
  end
  local right = detail(workers.get(S.selected), wide and w - lw - 3 or w)
  S.detail_offset = math.max(0, math.min(S.detail_offset or 0, math.max(0, #right - body)))
  if #list == 0 then left = right end
  for i = 1, body do
    local l = (not wide and S.detail and right[i + S.detail_offset] or left[i]) or { '', 'WorkerText' }
    local r = right[i + S.detail_offset] or { '', 'WorkerText' }
    row(l[1], l[2], wide and r[1] or nil, r[2], wide and lw or nil)
  end
  row(string.rep('─', w), 'WorkerBorder')
  row(' n new  N workspace  Enter chat  p prompt  r rename  s stop', 'WorkerKey')
  row(' a delegate  m peer  d dismiss  Tab detail  [/] scroll  q close', 'WorkerKey')
  vim.bo[S.buf].modifiable = true
  api.nvim_buf_set_lines(S.buf, 0, -1, false, lines)
  api.nvim_buf_clear_namespace(S.buf, ns, 0, -1)
  for _, m in ipairs(marks) do if m.finish > m.col then api.nvim_buf_set_extmark(S.buf, ns, m.row, m.col, { end_col = m.finish, hl_group = m.group }) end end
  vim.bo[S.buf].modifiable = false
end
local function notify(err) if err then vim.notify(clean(err), vim.log.levels.WARN) end end
local function input(prompt, default, limit, fn)
  vim.ui.input({ prompt = prompt, default = default or '' }, function(text)
    if not text or text:match('^%s*$') then return end
    if #text > limit then notify('Input exceeds ' .. limit .. ' bytes'); return end
    fn(text)
  end)
end
local function selected(fn) local r = workers.get(S.selected); if r then fn(r) end end
function M.close()
  if S.win and api.nvim_win_is_valid(S.win) then api.nvim_win_close(S.win, true) end
  S.win, S.buf = nil, nil
end
function M.action(key)
  if key == 'q' then return M.close() end
  if key == 'j' or key == 'k' then
    local list, i = records(); i = math.max(1, math.min(#list, i + (key == 'j' and 1 or -1)))
    S.selected = list[i] and list[i].id; S.detail_offset = 0; M.render(); return
  end
  if key == '[' or key == ']' then S.detail_offset = math.max(0, (S.detail_offset or 0) + (key == ']' and 5 or -5)); M.render(); return end
  if key == '<Tab>' then S.detail = not S.detail; M.render(); return end
  if key == 'n' or key == 'N' then
    local cwd = S.cwd
    local function create(path)
      input('Worker task: ', '', 12000, function(task)
        if S.origin and api.nvim_win_is_valid(S.origin) then M.close(); api.nvim_set_current_win(S.origin) end
        local ok, result, err = pcall(workers.new, { task = task, cwd = path })
        if not ok then notify(result) elseif not result then notify(err) end
      end)
    end
    if key == 'N' then input('Workspace: ', cwd, 4096, function(path) create(vim.fn.fnamemodify(vim.fn.expand(path), ':p')) end) else create(cwd) end
    return
  end
  selected(function(r)
    local id = r.id
    if key == '<CR>' then M.close(); local ok, err = workers.open(id); if ok == nil then notify(err) end
    elseif key == 's' then local _, err = workers.stop(id); notify(err)
    elseif key == 'd' then local _, err = workers.dismiss(id); notify(err)
    elseif key == 'r' then input('Worker name: ', r.name, 80, function(name) local _, err = workers.rename(id, name); notify(err) end)
    elseif key == 'p' or key == 'a' then
      input(key == 'a' and 'Delegate via parent: ' or 'Prompt (queued while busy): ', '', 12000, function(text)
        if key == 'a' then text = 'Delegate this task to child agents using the available collaboration tools, then report their results: ' .. text end
        local _, err = workers.send(id, text); notify(err)
      end)
    elseif key == 'm' then
      local peers = {}; for _, peer in ipairs(workers.list()) do if peer.id ~= id then peers[#peers + 1] = peer end end
      vim.ui.select(peers, { prompt = 'Send from ' .. clean(r.name) .. ' to:', format_item = function(peer) return clean(peer.name) .. ' / ' .. peer.id end }, function(peer)
        if peer then input('Peer message: ', '', 8000, function(text) local _, err = workers.peer(id, peer.id, text); notify(err) end) end
      end)
    end
  end)
  M.render()
end
local function geometry()
  local width, height = math.max(1, vim.o.columns - 4), math.max(1, vim.o.lines - 5)
  return { relative = 'editor', width = width, height = height, row = 1, col = math.min(1, vim.o.columns - width), style = 'minimal', border = 'rounded', title = ' WORKERS / independent sessions + delegated activity ', title_pos = 'center' }
end
function M.open()
  if visible() then api.nvim_set_current_win(S.win); return M.render() end
  M.close()
  vim.cmd.stopinsert()
  S.origin = api.nvim_get_current_win()
  local ok, agent = pcall(require, 'spaceghost.agent')
  S.cwd = ok and agent.cwd() or vim.fn.getcwd()
  S.buf = api.nvim_create_buf(false, true)
  vim.bo[S.buf].bufhidden = 'wipe'; vim.bo[S.buf].filetype = 'spaceghost-workers'
  S.win = api.nvim_open_win(S.buf, true, geometry())
  vim.wo[S.win].winhighlight = 'Normal:WorkerNormal,FloatBorder:WorkerBorder,FloatTitle:WorkerTitle'
  vim.wo[S.win].wrap = false; vim.wo[S.win].cursorline = false
  for _, key in ipairs({ 'n', 'N', '<CR>', 'p', 'r', 's', 'a', 'd', 'm', 'j', 'k', '[', ']', '<Tab>', 'q' }) do
    vim.keymap.set('n', key, function() M.action(key) end, { buffer = S.buf, nowait = true, silent = true })
  end
  vim.keymap.set('n', '<Esc>', M.close, { buffer = S.buf, nowait = true })
  M.render()
  local win = S.win
  vim.schedule(function()
    -- A terminal's pending startinsert must not leak into a read-only cockpit.
    if S.win == win and api.nvim_get_current_win() == win then vim.cmd.stopinsert() end
  end)
end
function M.statusline()
  local c = workers.summary()
  if (c.total or 0) == 0 then return '' end
  return '%#SpaceghostStatusBranch# CX ' .. (c.running or 0) .. ' active %#SpaceghostStatusWarn#' .. (c.waiting or 0) .. ' wait %#SpaceghostStatusCwd#' .. (c.done or 0) .. ' done' .. ((c.failed or 0) > 0 and ' %#SpaceghostStatusAlert#' .. c.failed .. ' failed' or '') .. ((c.unread or 0) > 0 and ' %#SpaceghostStatusWarn#' .. c.unread .. ' inbox' or '') .. ' '
end
function M.setup()
  -- Clean up a clock left by an earlier configuration version during live reload.
  if S.timer then S.timer:stop(); if not S.timer:is_closing() then S.timer:close() end; S.timer = nil end
  api.nvim_create_user_command('CodexWorkers', M.open, { desc = 'Open native Codex worker dashboard', force = true })
  workers.subscribe('worker-ui', function(reason)
    -- Replaced on reload through the stable subscription key. No hidden redraw loop.
    if reason == 'tick' and vim.g.spaceghost_worker_motion == false then return end
    if not visible() or S.pending then return end
    S.pending = true
    vim.schedule(function() S.pending = false; M.render() end)
  end)
  local group = api.nvim_create_augroup('SpaceghostWorkerUI', { clear = true })
  api.nvim_create_autocmd('VimResized', { group = group, callback = function() if visible() then api.nvim_win_set_config(S.win, geometry()); M.render() end end })
  api.nvim_create_autocmd('TabEnter', { group = group, callback = M.render })
  api.nvim_create_autocmd('WinClosed', { group = group, callback = function(ev) if tonumber(ev.match) == S.win then S.win, S.buf = nil, nil end end })
  api.nvim_create_autocmd('VimLeavePre', { group = group, callback = M.close })
  M.render()
end
return M
