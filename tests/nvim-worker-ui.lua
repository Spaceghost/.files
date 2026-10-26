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
