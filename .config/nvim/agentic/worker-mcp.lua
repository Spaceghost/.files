-- Minimal MCP JSONL stdio process. stdout is reserved for protocol frames.
local uv = vim.uv
local LIMIT, MAX_PENDING = 65536, 16
local socket, token = vim.env.SPACEGHOST_WORKER_SOCKET, vim.env.SPACEGHOST_WORKER_TOKEN
local input, output = uv.new_pipe(false), uv.new_pipe(false)
assert(input:open(0))
assert(output:open(1))
local stopped, pending, connections = false, 0, {}
local function close(handle) if handle and not handle:is_closing() then handle:close() end end
local function emit(value)
  local ok, frame = pcall(vim.json.encode, value)
  if not ok or #frame > LIMIT then
    frame = vim.json.encode({ jsonrpc = '2.0', id = value.id or vim.NIL, error = { code = -32603, message = 'Response exceeds frame limit' } })
  end
  if not stopped then output:write(frame .. '\n') end
end
local function protocol_error(id, code, message)
  emit({ jsonrpc = '2.0', id = id or vim.NIL, error = { code = code, message = message } })
end
local function tool_result(id, result, failure)
  emit({ jsonrpc = '2.0', id = id, result = { content = { { type = 'text', text = failure or vim.json.encode(result) } }, isError = failure ~= nil } })
end
local function bridge(id, params)
  if pending >= MAX_PENDING then tool_result(id, nil, 'Too many pending requests'); return end
  if not socket or not token then tool_result(id, nil, 'Worker bridge unavailable'); return end
  local pipe, timer = uv.new_pipe(false), uv.new_timer()
  pending = pending + 1
  connections[pipe] = timer
  local complete, buffer = false, ''
  local function finish(result, failure)
    if complete then return end
    complete = true
    pending = pending - 1
    connections[pipe] = nil
    close(timer)
    close(pipe)
    vim.schedule(function() tool_result(id, result, failure) end)
  end
  timer:start(3000, 0, function() finish(nil, 'Worker bridge timed out') end)
  pipe:connect(socket, function(err)
    if complete then return end
    if err then finish(nil, 'Worker bridge unavailable'); return end
    local encoded = vim.json.encode({ token = token, name = params.name, arguments = params.arguments or {} }) .. '\n'
    if #encoded > LIMIT then finish(nil, 'Request exceeds frame limit'); return end
    pipe:write(encoded, function(write_error) if write_error then finish(nil, 'Worker bridge write failed') end end)
    pipe:read_start(function(read_error, data)
      if complete then return end
      if read_error or not data then finish(nil, 'Worker bridge disconnected'); return end
      if #buffer + #data > LIMIT + 1 then finish(nil, 'Response exceeds frame limit'); return end
      buffer = buffer .. data
      local newline = buffer:find('\n', 1, true)
      if not newline then return end
      local ok, response = pcall(vim.json.decode, buffer:sub(1, newline - 1))
      if not ok or type(response) ~= 'table' then finish(nil, 'Invalid bridge response')
      elseif response.ok then finish(response.result)
      else finish(nil, response.error or 'Worker bridge rejected request') end
    end)
  end)
end
local function schema(properties, required)
  return { type = 'object', properties = properties or vim.empty_dict(), required = required or {}, additionalProperties = false }
end
local tools = {
  { name = 'workers_list', description = 'List peers as {workers,total,next_offset}. Repeat with next_offset until absent. Status fields are bounded; plan is a step count.', inputSchema = schema({ offset = { type = 'integer', minimum = 0 }, limit = { type = 'integer', minimum = 1, maximum = 100 } }) },
  { name = 'workers_status', description = 'Read worker status; defaults to yourself.', inputSchema = schema({ worker_id = { type = 'string' } }) },
  { name = 'workers_send', description = 'Send a peer a message and receive {id,from,to,status,at}. Busy peers receive messages in order; no automatic acknowledgement is generated.', inputSchema = schema({ worker_id = { type = 'string' }, message = { type = 'string', maxLength = 16384 }, reply_to = { type = 'string' } }, { 'worker_id', 'message' }) },
  { name = 'workers_inbox', description = 'Read your inbox as {messages,total,next_offset}. Prompts are omitted. Repeat with next_offset; if the last message has next_text_offset, pass it as text_offset to continue that message at next_offset. Otherwise reset text_offset to zero.', inputSchema = schema({ offset = { type = 'integer', minimum = 0 }, limit = { type = 'integer', minimum = 1, maximum = 100 }, text_offset = { type = 'integer', minimum = 0 } }) },
}
local function receive(frame)
  local ok, request = pcall(vim.json.decode, frame)
  if not ok then protocol_error(nil, -32700, 'Parse error'); return end
  if type(request) ~= 'table' or request.jsonrpc ~= '2.0' or type(request.method) ~= 'string' then protocol_error(nil, -32600, 'Invalid Request'); return end
  local id = request.id
  if id == nil then return end -- MCP notifications never receive a response.
  if type(id) ~= 'string' and type(id) ~= 'number' then protocol_error(nil, -32600, 'Invalid request ID'); return end
  if type(id) == 'string' and #id > 256 then protocol_error(nil, -32600, 'Request ID exceeds limit'); return end
  local params = request.params or {}
  if type(params) ~= 'table' then protocol_error(id, -32602, 'Invalid params'); return end
  if request.method == 'initialize' then
    local versions = { ['2024-11-05'] = true, ['2025-03-26'] = true, ['2025-06-18'] = true, ['2025-11-25'] = true }
    local version = versions[params.protocolVersion] and params.protocolVersion or '2024-11-05'
    emit({ jsonrpc = '2.0', id = id, result = { protocolVersion = version, capabilities = { tools = { listChanged = false } }, serverInfo = { name = 'spaceghost-workers', version = '1.0.0' } } })
  elseif request.method == 'ping' then emit({ jsonrpc = '2.0', id = id, result = vim.empty_dict() })
  elseif request.method == 'tools/list' then emit({ jsonrpc = '2.0', id = id, result = { tools = tools } })
  elseif request.method == 'tools/call' then
    if type(params.name) ~= 'string' or (params.arguments ~= nil and type(params.arguments) ~= 'table') then protocol_error(id, -32602, 'Invalid tool arguments'); return end
    bridge(id, params)
  else protocol_error(id, -32601, 'Method not found') end
end
local buffer, discarding = '', false
input:read_start(function(err, data)
  if err or not data then
    stopped = true
    close(input)
    for pipe, timer in pairs(connections) do close(pipe); close(timer) end
    return
  end
  local start = 1
  while start <= #data do
    local newline = data:find('\n', start, true)
    local fragment = data:sub(start, newline and newline - 1 or #data)
    if not discarding then
      if #buffer + #fragment > LIMIT then
        buffer, discarding = '', true
        vim.schedule(function() protocol_error(nil, -32600, 'Request exceeds frame limit') end)
      else buffer = buffer .. fragment end
    end
    if newline then
      if not discarding and #buffer > 0 then
        local frame = buffer
        vim.schedule(function() receive(frame) end)
      end
      buffer, discarding = '', false
      start = newline + 1
    else break end
  end
end)
while not stopped do vim.wait(1000, function() return stopped end, 10) end
close(output)
