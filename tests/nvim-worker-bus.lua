local root = vim.fn.fnamemodify(debug.getinfo(1, 'S').source:sub(2), ':h:h')
package.path = root .. '/.config/nvim/lua/?.lua;' .. package.path
local function check(value, message) assert(value, message) end
local records = {
  alpha = { id = 'alpha', name = 'Alpha', cwd = root, status = 'ready', inbox = {}, queue = {} },
  beta = { id = 'beta', name = 'Beta', cwd = root, status = 'working', inbox = {}, queue = {} },
}
package.loaded['spaceghost.workers'] = {
  get = function(id) return records[id] end,
  list = function() return { records.alpha, records.beta } end,
  peer = function(from, to, text, opts)
    if not records[to] then return nil, 'Unknown worker' end
    local message = { id = 'm' .. (#records[to].inbox + 1), from = from, to = to, text = text, reply_to = opts.reply_to, state = 'queued' }
    table.insert(records[to].inbox, message)
    table.insert(records[to].queue, message)
    return message
  end,
}
local bus = require('spaceghost.worker_bus')
local clients = {}
local function raw_socket(path, frame)
  local pipe = vim.uv.new_pipe(false)
  local done, received = false, ''
  pipe:connect(path, function(err)
    check(not err, err)
    pipe:write(frame)
    pipe:read_start(function(_, data)
      if data then received = received .. data else done = true; pipe:close() end
    end)
  end)
  check(vim.wait(6000, function() return done end, 10), 'socket response timeout')
  return received
end
local function client(descriptor, token)
  local env = {}
  for _, item in ipairs(descriptor.env) do env[item.name] = item.value end
  if token then env.SPACEGHOST_WORKER_TOKEN = token end
  local replies, partial, errors = {}, '', ''
  local command = { descriptor.command }
  vim.list_extend(command, descriptor.args)
  local job = vim.fn.jobstart(command, {
    env = env,
    on_stdout = function(_, data)
      for i, line in ipairs(data) do
        partial = partial .. line
        if i < #data then
          if partial ~= '' then check(#partial <= 65536, 'outer MCP frame exceeds limit'); local ok, decoded = pcall(vim.json.decode, partial); check(ok, 'non-JSON stdout: ' .. partial); table.insert(replies, decoded) end
          partial = ''
        end
      end
    end,
    on_stderr = function(_, data) errors = errors .. table.concat(data, '\n') end,
  })
  check(job > 0, 'helper failed to start')
  table.insert(clients, job)
  local sequence = 0
  return function(method, params, raw)
    sequence = sequence + 1
    local id = sequence
    vim.fn.chansend(job, raw or (vim.json.encode({ jsonrpc = '2.0', id = id, method = method, params = params or {} }) .. '\n'))
    check(vim.wait(4000, function()
      for _, reply in ipairs(replies) do if reply.id == id or (raw and reply.error) then return true end end
      return false
    end, 10), 'response timeout: ' .. method .. ' stderr=' .. errors)
    for i, reply in ipairs(replies) do if reply.id == id or (raw and reply.error) then table.remove(replies, i); return reply end end
  end
end
local ok, err = xpcall(function()
  local descriptor = bus.descriptor('alpha')
  check(vim.uv.fs_stat(bus.ensure()).mode % 512 == 384, 'socket must be 0600')
  check(vim.uv.fs_stat(vim.fn.fnamemodify(bus.ensure(), ':h')).mode % 512 == 448, 'private directory must be 0700')
  check(vim.json.decode(raw_socket(bus.ensure(), '{bad}\n')).ok == false, 'malformed socket request')
  check(raw_socket(bus.ensure(), string.rep('x', 65538) .. '\n') == '', 'oversized socket frame disconnected')
  local call = client(descriptor)
  check(call('initialize').result.protocolVersion, 'initialize')
  check(#call('tools/list').result.tools == 4, 'tool directory')
  local function tool(name, args) return call('tools/call', { name = name, arguments = args or {} }) end
  local result = tool('workers_list').result
  check(vim.json.decode(result.content[1].text).workers[2].id == 'beta', 'list workers')
  tool('workers_send', { worker_id = 'beta', message = 'one', from = 'spoof' })
  tool('workers_send', { worker_id = 'beta', message = 'two' })
  check(records.beta.queue[1].from == 'alpha' and records.beta.queue[2].text == 'two', 'authenticated ordered sends')
  local beta = client(bus.descriptor('beta'))
  local inbox = beta('tools/call', { name = 'workers_inbox', arguments = {} }).result
  check(#vim.json.decode(inbox.content[1].text).messages == 2, 'own inbox')
  local large = string.rep('"\\', 8192)
  local before = #records.beta.queue
  for _ = 1, 2 do
    local receipt = tool('workers_send', { worker_id = 'beta', message = large }).result
    check(not receipt.isError, 'legal large send must succeed')
    local decoded = vim.json.decode(receipt.content[1].text)
    check(decoded.id and not decoded.text and not decoded.prompt, 'compact send receipt')
  end
  check(#records.beta.queue == before + 2, 'large sends enqueue exactly once')
  local offset, text_offset, recovered = 2, 0, ''
  repeat
    local reply = beta('tools/call', { name = 'workers_inbox', arguments = { offset = offset, limit = 1, text_offset = text_offset } }).result
    check(not reply.isError, 'large inbox fits outer MCP frame')
    local page = vim.json.decode(reply.content[1].text)
    check(#page.messages == 1 and not page.messages[1].prompt, 'public inbox only')
    recovered = recovered .. page.messages[1].text
    text_offset = page.messages[1].next_text_offset
  until not text_offset
  check(recovered == large, 'paged text preserved exactly')
  records.beta.inbox[#records.beta.inbox + 1] = {
    id = 'escaped', from = 'alpha', to = 'beta', text = string.rep('\1', 16384), prompt = string.rep('unused', 50000),
  }
  local escaped = beta('tools/call', { name = 'workers_inbox', arguments = { offset = 4 } }).result
  check(not escaped.isError and vim.json.decode(escaped.content[1].text).messages[1].next_text_offset, 'worst-case escaping fits and continues')
  records.beta.activity = string.rep('"\\', 100000)
  records.beta.plan = { { title = string.rep('"\\', 100000), status = 'completed' } }
  local status = tool('workers_status', { worker_id = 'beta' }).result
  check(not status.isError and vim.json.decode(status.content[1].text).plan.completed == 1, 'bounded status and plan summary')
  check(not tool('workers_list').result.isError, 'bounded list ignores unbounded telemetry')
  local engine = package.loaded['spaceghost.workers']
  local original_list, many = engine.list, {}
  for _ = 1, 120 do many[#many + 1] = records.beta end
  engine.list = function() return many end
  local seen, list_offset = 0, 0
  repeat
    local reply = tool('workers_list', { offset = list_offset, limit = 100 }).result
    check(not reply.isError, 'large worker directory fits frame')
    local page = vim.json.decode(reply.content[1].text)
    check(#page.workers > 0, 'directory pagination makes progress')
    seen = seen + #page.workers
    list_offset = page.next_offset
  until not list_offset
  check(seen == 120, 'directory pagination preserves all records')
  engine.list = original_list
  check(tool('workers_send', { worker_id = 'missing', message = 'x' }).result.isError, 'unknown recipient')
  local bad = client(descriptor, 'incorrect')
  check(bad('tools/call', { name = 'workers_list' }).result.isError, 'bad token rejected')
  local stale = client(bus.descriptor('removed'))
  check(stale('tools/call', { name = 'workers_list' }).result.isError, 'stale identity rejected')
  check(call('invalid', {}, '{oops}\n').error.code == -32700, 'malformed JSON')
  check(call('invalid', {}, string.rep('x', 65537) .. '\n').error, 'oversized frame')
  package.loaded['spaceghost.worker_bus'] = nil
  bus = require('spaceghost.worker_bus')
  check(bus.ensure() == descriptor.env[1].value, 'reload preserved socket')
  check(tool('workers_status').result.content, 'reload retained identity')
  bus.revoke('alpha')
  check(tool('workers_list').result.isError, 'revoked token rejected')
  bus.close()
  check(beta('tools/call', { name = 'workers_list' }).result.isError, 'dead socket handled')
end, debug.traceback)
for _, job in ipairs(clients) do pcall(vim.fn.jobstop, job) end
bus.close()
if not ok then error(err) end
print('worker bus tests passed')
vim.cmd('qa!')
