-- nvim --headless -u NONE -l tests/nvim-worker-ui.lua
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
vim.g.spaceghost_no_shell = true
local records, subscribers, calls = {}, {}, {}
for i = 1, 80 do
  records[i] = { id = 'w' .. i, name = 'Worker ' .. i, cwd = '/tmp/workspace', status = i == 2 and 'waiting' or 'working', activity = 'Inspecting source', started_at = os.time() - 90, plan = { { content = 'Read source', status = 'completed' }, { content = 'Implement', status = 'in_progress' } }, usage = { used = 25, size = 100 }, inbox = { { from_name = 'Peer', text = 'An update', status = 'delivered' } }, children = { child = { name = 'Review helper', status = 'working' } } }
end
local engine = {
  list = function() return records end,
  get = function(id) for _, r in ipairs(records) do if r.id == id then return r end end end,
  summary = function() return { total = #records, running = 79, waiting = 1, failed = 0, done = 0, unread = 2 } end,
  subscribe = function(key, cb) subscribers[key] = cb end,
}
for _, action in ipairs({ 'new', 'open', 'send', 'peer', 'stop', 'rename', 'dismiss' }) do engine[action] = function(...) calls[#calls + 1] = { action, ... }; return {} end end
package.loaded['spaceghost.workers'] = engine
local ui = require('spaceghost.worker_ui')
local failures = 0
local function test(name, fn)
  local ok, err = pcall(fn)
  if ok then print('PASS ' .. name) else failures = failures + 1; io.stderr:write('FAIL ' .. name .. ': ' .. tostring(err) .. '\n') end
end
local function text() return table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\n') end
local function state() return _G.__spaceghost_worker_ui end
local function answer(value) vim.ui.input = function(_, cb) cb(value) end end
ui.setup()
test('wide view renders real progress and only visible cards', function()
  vim.o.columns = 140; vim.o.lines = 42; ui.open()
  assert(text():find('SELECTED / Worker 1', 1, true)); assert(text():find('25% used', 1, true))
  assert(text():find('1/2 plan', 1, true)); assert(not text():find('Worker 80', 1, true)); assert(not state().timer)
  assert(#vim.api.nvim_buf_get_lines(0, 0, -1, false) <= 40)
end)
test('keyboard selection scrolls many workers without cursor jumps', function()
  local cursor = vim.api.nvim_win_get_cursor(0)
  for _ = 1, 79 do ui.action('j') end
  assert(state().selected == 'w80'); assert(text():find('Worker 80', 1, true))
  assert(vim.deep_equal(cursor, vim.api.nvim_win_get_cursor(0)))
  local first = table.remove(records, 1); ui.render(); assert(state().selected == 'w80'); table.insert(records, 1, first)
end)
test('narrow view toggles detail and scrolls inbox and children', function()
  ui.close(); vim.o.columns = 65; vim.o.lines = 24; ui.open(); ui.action('<Tab>')
  assert(text():find('SELECTED / Worker 80', 1, true)); assert(not text():find(' │ ', 1, true))
  for _ = 1, 6 do ui.action(']') end
  assert(text():find('Peer: An update', 1, true)); assert(text():find('Review helper', 1, true))
  for _, line in ipairs(vim.api.nvim_buf_get_lines(0, 0, -1, false)) do assert(vim.fn.strdisplaywidth(line) <= 61) end
end)
local function complete_record()
  local r = records[80]
  r.plan, r.inbox, r.children = {}, {}, {}
  for i = 1, 8 do
    r.plan[i] = { content = 'Reported step ' .. i, status = i == 1 and 'complete' or 'pending' }
    r.children['child-' .. i] = { id = 'child-' .. i, name = 'Helper ' .. i, status = 'working' }
  end
  for i = 1, 5 do
    r.inbox[i] = { id = 'message-' .. i, from = 'w1', text = 'Peer result ' .. i, status = i == 1 and 'queued' or 'delivered' }
  end
  state().detail_offset = 0
  ui.render()
  return r
end
local function all_detail()
  local pages = { text() }
  for _ = 1, 200 do
    local before = state().detail_offset
    ui.action(']'); pages[#pages + 1] = text()
    if state().detail_offset == before then return table.concat(pages, '\n') end
  end
  error('Detail scrolling did not reach the end')
end
test('detail scrolling reaches every reported plan step', function()
  complete_record()
  local content = all_detail()
  for i = 1, 8 do assert(content:find('Reported step ' .. i, 1, true), 'missing plan step ' .. i) end
end)
test('detail scrolling reaches every inbox message with identity and delivery state', function()
  complete_record()
  local content = all_detail()
  for i = 1, 5 do assert(content:find('message-' .. i, 1, true), 'missing message ID ' .. i); assert(content:find('Peer result ' .. i, 1, true), 'missing message body ' .. i) end
  assert(content:find('Worker 1 (w1)', 1, true), 'sender name and stable identity must be visible')
  assert(content:find('[queued]', 1, true) and content:find('[delivered]', 1, true), 'delivery states must be visible')
end)
test('detail scrolling reaches every child in stable ID order', function()
  complete_record()
  local content = all_detail()
  for i = 1, 8 do assert(content:find('Helper ' .. i, 1, true), 'missing child ' .. i) end
  ui.action('c')
  local page = text()
  assert(page:find('child-1', 1, true) and page:find('child-8', 1, true), 'child identities must be readable')
  assert(page:find('Helper 1', 1, true) < page:find('Helper 8', 1, true), 'children must sort by stable identity')
end)
test('long peer messages wrap full content without exposing terminal controls', function()
  local r = complete_record()
  r.inbox = { { id = 'long-message', from = 'w1', status = 'delivered', text = 'FIRST ' .. string.rep('界 source ', 30) .. '\nSECOND\tline\27[31m\0 LAST' } }
  state().detail_offset = 0; ui.render()
  local content = all_detail()
  assert(content:find('FIRST', 1, true) and content:find('SECOND', 1, true) and content:find('LAST', 1, true), 'all message paragraphs must remain readable')
  assert(not content:find('\27', 1, true) and not content:find('\0', 1, true), 'message controls must be sanitized')
  for _, line in ipairs(vim.api.nvim_buf_get_lines(0, 0, -1, false)) do assert(vim.fn.strdisplaywidth(line) <= 61) end
  assert(#vim.api.nvim_buf_get_lines(0, 0, -1, false) <= 19, 'render only the visible viewport')
end)
test('section jumps and help expose native navigation in narrow layouts', function()
  complete_record()
  ui.action('i'); assert(text():find('INBOX /', 1, true), 'i must jump to the inbox')
  ui.action('P'); assert(text():find('PLAN ', 1, true), 'P must jump to the plan')
  ui.action('G'); assert(text():find('Helper 8', 1, true), 'G must reach the last detail row')
  ui.action('g'); assert(text():find('SELECTED / Worker 80', 1, true), 'g must return to the selected header')
  assert(text():find('? help', 1, true), 'narrow footer must advertise help')
  ui.action('?')
  local help = all_detail()
  for _, control in ipairs({ 'P plan', 'i inbox', 'c children', 'g/G', 'j/k', 'Enter chat', 'm peer', 'q close' }) do assert(help:find(control, 1, true), 'missing help for ' .. control) end
  ui.action('?'); ui.action('j'); assert(state().selected == 'w80', 'selection remains on the last worker')
  ui.action('k'); assert(state().selected == 'w79' and state().detail_offset == 0, 'selection changes reset detail scrolling')
  ui.action('j')
end)
test('hidden narrow detail does no work proportional to large peer bodies', function()
  local r = complete_record()
  ui.action('<Tab>')
  r.inbox = { { id = 'large-message', from = 'w1', status = 'queued', text = string.rep('界', 5000) } }
  local original, count = vim.fn.strdisplaywidth, 0
  vim.fn.strdisplaywidth = function(value) count = count + 1; return original(value) end
  local ok, err = pcall(ui.render)
  vim.fn.strdisplaywidth = original
  assert(ok, err)
  assert(count < 2000, 'hidden detail wrapped the entire peer body (' .. count .. ' width checks)')
  ui.action('i')
  assert(text():find('界界', 1, true), 'inbox jump must reveal the complete body')
  count = 0
  vim.fn.strdisplaywidth = function(value) count = count + 1; return original(value) end
  ok, err = pcall(ui.render)
  vim.fn.strdisplaywidth = original
  assert(ok, err)
  assert(count < 2000, 'unchanged visible detail must reuse wrapped content')
  r.inbox[1].status = 'delivered'; ui.render()
  assert(text():find('[delivered]', 1, true), 'delivery state changes must invalidate cached metadata')
end)
test('resized detail keeps complete peer content and sanitizes C1 controls', function()
  local r = complete_record()
  r.inbox = { { id = 'resize-message', from = 'w1', status = 'delivered', text = 'START ' .. string.rep('界 résumé ', 30) .. '\nFINISH\194\155' } }
  ui.close(); vim.o.columns = 36; ui.open(); ui.action('i')
  local content = all_detail()
  assert(content:find('START', 1, true) and content:find('FINISH', 1, true), 'resizing must preserve all message content')
  assert(not content:find('\194\155', 1, true), 'C1 controls must not enter dashboard rows')
  for _, line in ipairs(vim.api.nvim_buf_get_lines(0, 0, -1, false)) do assert(vim.fn.strdisplaywidth(line) <= 32, 'resized line exceeds the window width') end
  ui.close(); vim.o.columns = 65; ui.open()
end)
test('adopted sessions report unavailable workspace instead of an invented origin', function()
  local r = records[80]
  local cwd = r.cwd
  r.cwd = nil; ui.action('g')
  local content = text()
  r.cwd = cwd; ui.render()
  assert(content:find('Workspace  unavailable (session predates tracking)', 1, true), 'unknown session origin needs an explicit unavailable label')
end)
test('controls target stable identity and bound prompt input', function()
  answer('Follow up'); ui.action('p'); assert(calls[#calls][1] == 'send' and calls[#calls][2] == 'w80')
  answer(string.rep('a', 12001)); local count = #calls; ui.action('p'); assert(#calls == count)
  answer('Readable name'); ui.action('r'); assert(calls[#calls][1] == 'rename')
  ui.action('s'); assert(calls[#calls][1] == 'stop' and calls[#calls][2] == 'w80')
  answer('Review changes'); ui.action('a'); assert(calls[#calls][3]:find('Delegate this task', 1, true))
  vim.ui.select = function(items, _, cb) cb(items[1]) end
  answer('Question'); ui.action('m'); assert(calls[#calls][1] == 'peer' and calls[#calls][2] == 'w80')
  ui.action('d'); assert(calls[#calls][1] == 'dismiss')
end)
test('motion disabled and hidden views ignore ticks; reload keeps one subscriber', function()
  vim.g.spaceghost_worker_motion = false; ui.render(); local tick = vim.api.nvim_buf_get_changedtick(state().buf)
  subscribers['worker-ui']('tick'); vim.wait(10); assert(vim.api.nvim_buf_get_changedtick(state().buf) == tick)
  subscribers['worker-ui']('change'); vim.wait(10); assert(vim.api.nvim_buf_get_changedtick(state().buf) > tick)
  vim.g.spaceghost_worker_motion = true
  tick = vim.api.nvim_buf_get_changedtick(state().buf); subscribers['worker-ui']('tick'); vim.wait(10); assert(vim.api.nvim_buf_get_changedtick(state().buf) > tick)
  package.loaded['spaceghost.worker_ui'] = nil; ui = require('spaceghost.worker_ui'); ui.setup()
  assert(not state().timer)
  local count = 0; for _ in pairs(subscribers) do count = count + 1 end; assert(count == 1)
  tick = vim.api.nvim_buf_get_changedtick(state().buf); vim.cmd.tabnew(); subscribers['worker-ui']('tick'); vim.wait(10); assert(vim.api.nvim_buf_get_changedtick(state().buf) == tick); vim.cmd.tabprevious()
  ui.close(); assert(not state().timer); subscribers['worker-ui'](); vim.wait(10); assert(not state().timer)
end)
test('new worker preserves origin workspace and chat focus', function()
  ui.open(); local cwd = state().cwd; answer('Implement this'); ui.action('n')
  assert(calls[#calls][1] == 'new' and calls[#calls][2].cwd == cwd)
  ui.open(); ui.action('<CR>'); assert(calls[#calls][1] == 'open' and calls[#calls][2] == 'w80')
end)
test('status summary and terminal mapping expose dashboard', function()
  assert(ui.statusline():find('79 active', 1, true)); assert(ui.statusline():find('1 wait', 1, true))
  require('spaceghost.keys').setup()
  local mapping = vim.fn.maparg('<C-\\>o', 't', false, true)
  assert(mapping.rhs == '<C-\\><C-N><Cmd>CodexWorkers<CR>' or mapping.rhs == '<C-\\><C-n><Cmd>CodexWorkers<CR>', vim.inspect(mapping))
end)
ui.close()
vim.cmd('cquit ' .. failures)
