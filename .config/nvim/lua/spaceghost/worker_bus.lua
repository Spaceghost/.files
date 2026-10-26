-- One private broker per editor. Tokens authorize identities, never request fields.
local M = {}
local uv = vim.uv
local MAX_FRAME, MAX_CLIENTS, TIMEOUT = 65536, 128, 5000
local state = rawget(_G, '__spaceghost_worker_bus')
if not state then
  state = { tokens = {}, clients = {} }
  rawset(_G, '__spaceghost_worker_bus', state)
end
local source = debug.getinfo(1, 'S').source:sub(2)
local helper = vim.fn.fnamemodify(source, ':p:h:h:h') .. '/agentic/worker-mcp.lua'
local function dispose(handle)
  if handle and not handle:is_closing() then handle:close() end
end
local function disconnect(client)
  if not state.clients[client] then return end
  dispose(state.clients[client].timer)
  state.clients[client] = nil
  dispose(client)
end
local function clipped(value, bytes)
  if type(value) ~= 'string' then return nil end
  if #value <= bytes then return value end
  local ending = bytes
  while ending > 0 and value:byte(ending + 1) >= 128 and value:byte(ending + 1) < 192 do ending = ending - 1 end
  return value:sub(1, ending)
end
local function public(record)
  local result = {}
  for key, bytes in pairs({ id = 128, name = 256, cwd = 1024, status = 32, activity = 512, model = 128, error = 512 }) do
    result[key] = clipped(record[key], bytes)
  end
  for _, key in ipairs({ 'started_at', 'finished_at', 'last_at', 'unread' }) do
    if type(record[key]) == 'number' then result[key] = record[key] end
  end
  if type(record.bridge) == 'boolean' then result.bridge = record.bridge end
  if type(record.usage) == 'table' then
    result.usage = {}
    for _, key in ipairs({ 'used', 'size' }) do if type(record.usage[key]) == 'number' then result.usage[key] = record.usage[key] end end
  end
  if type(record.plan) == 'table' then
    result.plan = { total = #record.plan, completed = 0 }
    for _, entry in ipairs(record.plan) do
      if type(entry) == 'table' and (entry.status == 'completed' or entry.status == 'done') then result.plan.completed = result.plan.completed + 1 end
    end
  end
  return result
end
-- Check both wire representations: the socket envelope and MCP's JSON encoded
-- text nested inside another JSON envelope. Leave room for the bounded request ID.
local function fits(result)
  local inner = vim.json.encode(result)
  local outer = vim.json.encode({ jsonrpc = '2.0', id = string.rep('x', 256), result = {
    content = { { type = 'text', text = inner } }, isError = false,
  } })
  return #outer <= 62000 and #vim.json.encode({ ok = true, result = result }) <= 62000
end
local function page_args(args)
  local offset, limit = args.offset or 0, args.limit or 20
  if type(offset) ~= 'number' or offset < 0 or offset % 1 ~= 0 or type(limit) ~= 'number' or limit < 1 or limit > 100 or limit % 1 ~= 0 then
    error('offset must be a nonnegative integer; limit must be 1–100')
  end
  return offset, limit
end
local function directory(records, args)
  local offset, limit = page_args(args)
  local result = { workers = {}, total = #records }
  for index = offset + 1, math.min(#records, offset + limit) do
    result.workers[#result.workers + 1] = public(records[index])
    result.next_offset = index < #records and index or nil
    if not fits(result) then
      table.remove(result.workers)
      result.next_offset = index - 1
      break
    end
  end
  return result
end
local function inbox(messages, args)
  local offset, limit = page_args(args)
  local text_offset = args.text_offset or 0
  if type(text_offset) ~= 'number' or text_offset < 0 or text_offset % 1 ~= 0 then error('Invalid text_offset') end
  local result = { messages = {}, total = #messages }
  for index = offset + 1, math.min(#messages, offset + limit) do
    local message, item = messages[index], {}
    for _, key in ipairs({ 'id', 'from', 'to', 'reply_to', 'status', 'state' }) do item[key] = clipped(message[key], 256) end
    for _, key in ipairs({ 'at', 'hops', 'created_at', 'delivered_at' }) do if type(message[key]) == 'number' then item[key] = message[key] end end
    local text = type(message.text) == 'string' and message.text or ''
    item.text_offset = index == offset + 1 and math.min(text_offset, #text) or 0
    -- At most 8192 bytes also fits worst-case control-character escaping twice.
    item.text = clipped(text:sub(item.text_offset + 1), 8192)
    local ending = item.text_offset + #item.text
    if ending < #text then item.next_text_offset = ending end
    result.messages[#result.messages + 1] = item
    result.next_offset = item.next_text_offset and index - 1 or (index < #messages and index or nil)
    -- Metadata is bounded too, but still account for its escape cost rather
    -- than assuming the maximum text chunk will always fit the first item.
    while #result.messages == 1 and not fits(result) and #item.text > 0 do
      item.text = clipped(item.text, math.floor(#item.text / 2))
      item.next_text_offset = item.text_offset + #item.text
      result.next_offset = index - 1
    end
    if not fits(result) then
      table.remove(result.messages)
      result.next_offset = index - 1
      break
    end
    if item.next_text_offset then break end
  end
  return result
end
function M._dispatch(request)
  if type(request) ~= 'table' or type(request.token) ~= 'string' then error('Unauthorized worker') end
  local identity = state.tokens[request.token]
  local workers = require('spaceghost.workers')
  if not identity or not workers.get(identity) then error('Unauthorized or stale worker') end
  local args = request.arguments or {}
  if type(args) ~= 'table' then error('Arguments must be an object') end
  if request.name == 'workers_list' then
    return directory(workers.list(), args)
  elseif request.name == 'workers_status' then
    local record = workers.get(args.worker_id or identity)
    if not record then error('Unknown worker') end
    return public(record)
  elseif request.name == 'workers_inbox' then
    return inbox(workers.get(identity).inbox or {}, args)
  elseif request.name == 'workers_send' then
    if type(args.worker_id) ~= 'string' or type(args.message) ~= 'string' or #args.message == 0 or #args.message > 16384 then
      error('worker_id and message (1–16384 bytes) are required')
    end
    if args.reply_to ~= nil and (type(args.reply_to) ~= 'string' or #args.reply_to > 256) then error('Invalid reply_to') end
    local message, err = workers.peer(identity, args.worker_id, args.message, { reply_to = args.reply_to })
    if not message then error(err or 'Message rejected') end
    -- Mutation has already succeeded: return a small receipt, never duplicate the
    -- original text/prompt into a response that could make success look like failure.
    return { id = clipped(message.id, 256), from = clipped(message.from, 128),
      to = clipped(message.to, 128), status = clipped(message.status or message.state or 'queued', 32),
      at = type(message.at) == 'number' and message.at or os.time() }
  end
  error('Unknown tool')
end
local function respond(client, request)
  if not state.clients[client] then return end
  local ok, result = pcall(function() return require('spaceghost.worker_bus')._dispatch(request) end)
  local encoded_ok, encoded = pcall(vim.json.encode, ok and { ok = true, result = result } or { ok = false, error = tostring(result) })
  if not encoded_ok or #encoded > MAX_FRAME then encoded = vim.json.encode({ ok = false, error = 'Response exceeds frame limit' }) end
  client:write(encoded .. '\n', function() disconnect(client) end)
end
function M.ensure()
  if state.server and not state.server:is_closing() then return state.path end
  local cache = vim.fn.stdpath('cache')
  vim.fn.mkdir(cache, 'p', 448)
  local directory, err = uv.fs_mkdtemp(cache .. '/workers-XXXXXX')
  assert(directory, err)
  uv.fs_chmod(directory, 448)
  local path = directory .. '/bus.sock'
  local server = uv.new_pipe(false)
  local ok, failure = server:bind(path)
  if not ok then dispose(server); uv.fs_rmdir(directory); error(failure) end
  uv.fs_chmod(path, 384)
  state.path, state.directory, state.server = path, directory, server
  server:listen(MAX_CLIENTS, function(accept_error)
    if accept_error then return end
    local client = uv.new_pipe(false)
    if not server:accept(client) then dispose(client); return end
    local count = 0
    for _ in pairs(state.clients) do count = count + 1 end
    if count >= MAX_CLIENTS then dispose(client); return end
    local timer = uv.new_timer()
    local connection = { timer = timer, buffer = '', complete = false }
    state.clients[client] = connection
    timer:start(TIMEOUT, 0, function() disconnect(client) end)
    client:read_start(function(read_error, data)
      if read_error or not data then disconnect(client); return end
      if connection.complete then return end
      if #connection.buffer + #data > MAX_FRAME + 1 then disconnect(client); return end
      connection.buffer = connection.buffer .. data
      local newline = connection.buffer:find('\n', 1, true)
      if not newline then return end
      connection.complete = true
      client:read_stop()
      local frame = connection.buffer:sub(1, newline - 1)
      vim.schedule(function()
        local decoded, request = pcall(vim.json.decode, frame)
        if not decoded then request = {} end
        respond(client, request)
      end)
    end)
  end)
  return path
end
function M.descriptor(worker_id)
  assert(type(worker_id) == 'string' and worker_id ~= '', 'Worker ID required')
  local path = M.ensure()
  local token
  for secret, id in pairs(state.tokens) do if id == worker_id then token = secret; break end end
  if not token then
    token = (assert(uv.random(32))):gsub('.', function(c) return string.format('%02x', c:byte()) end)
    state.tokens[token] = worker_id
  end
  return {
    name = 'spaceghost-workers', command = vim.v.progpath,
    args = { '--headless', '-u', 'NONE', '-i', 'NONE', '-l', helper },
    env = {
      { name = 'SPACEGHOST_WORKER_SOCKET', value = path },
      { name = 'SPACEGHOST_WORKER_TOKEN', value = token },
      { name = 'SPACEGHOST_WORKER_ID', value = worker_id },
    },
  }
end
function M.revoke(worker_id)
  for token, id in pairs(state.tokens) do if id == worker_id then state.tokens[token] = nil end end
end
function M.close()
  local clients = {}
  for client in pairs(state.clients) do clients[#clients + 1] = client end
  for _, client in ipairs(clients) do disconnect(client) end
  dispose(state.server)
  state.server = nil
  if state.path then uv.fs_unlink(state.path) end
  if state.directory then uv.fs_rmdir(state.directory) end
  state.path, state.directory, state.tokens = nil, nil, {}
end
local group = vim.api.nvim_create_augroup('SpaceghostWorkerBus', { clear = true })
vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function() require('spaceghost.worker_bus').close() end })
return M
