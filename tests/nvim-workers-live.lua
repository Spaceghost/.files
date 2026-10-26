-- Installed Agentic + live Codex + actual Lua MCP bridge. Creates isolated workspaces.
-- nvim --headless -u NONE -l tests/nvim-workers-live.lua [--live]
vim.g.spaceghost_no_shell = true
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')
vim.o.columns, vim.o.lines = 180, 55
local W = require('spaceghost.workers')
local root = vim.fn.tempname()
vim.fn.mkdir(root .. '/alpha', 'p')
vim.fn.mkdir(root .. '/beta', 'p')
local function wait_for(description, fn, limit)
  assert(vim.wait(limit or 55000, function()
    if vim.tbl_contains(arg, '--live') then
      -- Approve only this test's directory/send MCP calls, never arbitrary tools.
      local registry = package.loaded['agentic.session_registry']
      for _, r in ipairs(W.list()) do
        local session = registry and registry.get(r.session_key)
        if session then
          for id, pending in pairs(session.permission_manager.pending) do
            local tracked = r.tools[pending.request.toolCall.toolCallId] or {}
            local title = pending.request.toolCall.title or ''
            if title == '' then title = tracked.title or '' end
            if title:find('workers_list', 1, true) or title:find('workers_send', 1, true)
              or (vim.tbl_contains(arg, '--delegated') and (title:find('spawn', 1, true) or title:find('wait', 1, true))) then
              for _, option in ipairs(pending.sorted_options) do
                if option.kind == 'allow_once' then
                  session.permission_manager:resolve(id, option.optionId)
                  break
                end
              end
            end
          end
        end
      end
    end
    return fn()
  end, 20), description .. ' timed out: ' .. vim.inspect(W.summary()))
end
local function history(r)
  local s = require('agentic.session_registry').get(r.session_key)
  local pieces = {}
  for _, m in ipairs(s.chat_history.messages) do if m.type == 'agent' then pieces[#pieces + 1] = m.text end end
  return table.concat(pieces, '\n')
end
local ok, err = pcall(function()
  local a = assert(W.new({ name = 'Alpha', cwd = root .. '/alpha' }))
  local b = assert(W.new({ name = 'Beta', cwd = root .. '/beta' }))
  wait_for('two concurrent sessions', function()
    local registry = require('agentic.session_registry')
    return a.session_id and b.session_id and registry.get(a.session_key).session_id
      and registry.get(b.session_key).session_id
  end)
  assert(a.bridge and b.bridge, 'peer MCP definitions missing')
  assert(a.id ~= b.id and a.tab ~= b.tab, 'workers share identity or tab')
  assert(a.cwd == root .. '/alpha' and b.cwd == root .. '/beta', 'workspaces crossed during initialization')
  W.open(a.id)
  assert(vim.api.nvim_get_current_tabpage() == a.tab, 'open moved worker out of its tab')
  vim.cmd('tabmove $')
  W.open(b.id)
  assert(vim.api.nvim_get_current_tabpage() == b.tab, 'tab reorder broke routing')
  -- The public new-session command must preserve the selected worker's view.
  local previous_tab, previous_key = b.tab, b.session_key
  vim.cmd.CodexNew()
  local fresh_tab = vim.api.nvim_get_current_tabpage()
  assert(fresh_tab ~= previous_tab, 'CodexNew reused the existing worker tab')
  local fresh
  for _, record in ipairs(W.list()) do
    if record.tab == fresh_tab then fresh = record end
  end
  assert(fresh and fresh.cwd == b.cwd, 'CodexNew lost the originating worker workspace')
  wait_for('new command session', function() return fresh.session_id ~= nil end)
  assert(require('agentic.session_registry').get(previous_key), 'CodexNew destroyed the previous worker')
  W.open(b.id)
  assert(vim.api.nvim_get_current_tabpage() == previous_tab, 'CodexNew detached the previous worker view')
  print('PASS CodexNew preserves existing worker and opens a separate workspace-bound tab')
  local old = a.id
  require('spaceghost.deck').reload()
  require('spaceghost.agent').load()
  W = require('spaceghost.workers')
  assert(W.get(old) == a and a.session_id, 'reload lost live worker')
  require('spaceghost.worker_ui').open()
  assert(vim.bo.filetype == 'spaceghost-workers', 'native dashboard did not open')
  require('spaceghost.worker_ui').close()
  print('PASS concurrent real sessions, peer bridge definitions, tab routing and reload')
  if vim.tbl_contains(arg, '--live') then
    assert(W.send(a.id, 'Call the workers_list MCP tool to discover your peer workers. Then reply PEER_DIRECTORY_OK and include the names Alpha and Beta from its result. Do not call filesystem or shell tools. Do not message a peer yet.'))
    assert(W.send(b.id, 'Reply exactly BETA_READY. Do not use tools or change files.'))
    wait_for('parallel Codex responses', function() return a.status == 'done' and b.status == 'done' end)
    assert(history(a):find('PEER_DIRECTORY_OK', 1, true), 'Alpha did not finish discovery')
    assert(history(a):find('Beta', 1, true), 'Alpha did not see peer name')
    local discovered = false
    for _, t in pairs(a.tools) do if t.title:find('workers_list', 1, true) then discovered = true end end
    assert(discovered, 'real workers_list tool call not observed')
    assert(history(b):find('BETA_READY', 1, true), 'Beta response missing')
    assert(W.send(a.id, 'Use the workers_send MCP tool to send worker ' .. b.id .. ' this message: "Reply exactly PEER_MESSAGE_OK. Do not use tools or change files." Then reply SENT_OK. Send once only.'))
    wait_for('real peer delivery', function()
      return #b.inbox > 0 and b.inbox[#b.inbox].status == 'delivered'
        and b.status == 'done' and a.status == 'done' and history(b):find('PEER_MESSAGE_OK', 1, true)
    end)
    assert(b.inbox[#b.inbox].from == a.id, 'peer provenance lost')
    print('PASS real Codex peer discovery, MCP send and automatic queued delivery')
    if vim.tbl_contains(arg, '--delegated') then
      assert(W.send(a.id, 'Delegate a tiny task to exactly one child agent using your native spawn_agent tool. Tell the child to reply CHILD_TELEMETRY_OK without tools or file changes. Wait for its result, then reply CHILD_DONE_OK. Do not use shell or filesystem tools.'))
      wait_for('delegated worker activity', function()
        return a.status == 'done' and next(a.children) ~= nil and history(a):find('CHILD_DONE_OK', 1, true)
      end, 110000)
      print('PASS native delegated child activity tracked under parent worker')
    end
  end
  for _, r in ipairs(W.list()) do
    if r.session_key then require('agentic').destroy_session({ session = r.session_key }) end
  end
end)
require('spaceghost.worker_bus').close()
vim.fn.delete(root, 'rf')
if not ok then io.stderr:write(tostring(err) .. '\n'); vim.cmd.cquit(1) end
vim.cmd('qa!')
