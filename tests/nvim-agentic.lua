-- Real installed-plugin/ACP smoke test. Optional --live sends one ChatGPT prompt.
-- Run from repo root: nvim --headless -u NONE -l tests/nvim-agentic.lua [--live]
vim.g.spaceghost_no_shell = true
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')
vim.o.columns = 160
vim.o.lines = 48
local root = vim.fn.tempname()
vim.fn.mkdir(root, 'p')
local file = root .. '/example.lua'
vim.fn.writefile({ 'return 42' }, file)
vim.cmd.edit(file)
local agent = require('spaceghost.agent')
local ok, err = pcall(function()
  assert(agent.cwd() == root, 'wrong editor workspace')
  assert(agent.load(), 'Agentic dependency missing')
  local config = require('agentic.config')
  local created, completed, chunks = nil, nil, {}
  config.hooks.on_create_session_response = function(data) created = data end
  config.hooks.on_response_complete = function(data) completed = data end
  config.hooks.on_session_update = function(data)
    local update = data.update
    if update.sessionUpdate == 'agent_message_chunk' and update.content.type == 'text' then
      chunks[#chunks + 1] = update.content.text
    end
  end
  agent.run('toggle')
  assert(vim.wait(45000, function() return created ~= nil end, 20), 'ACP session initialization timed out')
  assert(created.session_id, 'ACP session creation failed: ' .. vim.inspect(created.err))
  local registry = require('agentic.session_registry')
  local session = registry.sessions[created.session_key]
  assert(session and session.widget:is_open(), 'native chat did not open')
  assert(config.acp_configs.session_cwd() == root, 'workspace lost when chat took focus')
  for _, win in pairs(session.widget.win_nrs) do
    if vim.api.nvim_win_is_valid(win) then
      assert(vim.bo[vim.api.nvim_win_get_buf(win)].buftype ~= 'terminal', 'chat is a terminal wrapper')
    end
  end
  assert(vim.wait(5000, function() return session:can_submit_prompt() end, 20), 'session not ready for input')
  print('PASS native Agentic buffers and authenticated ACP session in editor workspace')
  if vim.tbl_contains(arg, '--live') then
    assert(session:_handle_input_submit('Reply with exactly SPACEGHOST_CODEX_OK. Do not use tools or change files.'), 'prompt rejected')
    assert(vim.wait(55000, function() return completed ~= nil end, 20), 'Codex response timed out')
    assert(completed.success, 'Codex response failed: ' .. vim.inspect(completed.error))
    assert(table.concat(chunks):find('SPACEGHOST_CODEX_OK', 1, true), 'missing streamed reply')
    print('PASS real Codex response streamed into native chat')
  end
  require('agentic').close()
  assert(not session.widget:is_open() and session.session_id, 'hiding chat lost session')
  vim.cmd.edit(file)
  agent.run('toggle')
  assert(session.widget:is_open(), 'hidden session did not reopen')
  require('agentic').destroy_session()
  print('PASS hide/reopen preserves session')
  local second = root .. '/second'
  vim.fn.mkdir(second, 'p')
  local next_file = second .. '/next.lua'
  vim.fn.writefile({ 'return 43' }, next_file)
  require('spaceghost.deck').reload()
  agent = require('spaceghost.agent')
  vim.cmd.edit(next_file)
  created = nil
  agent.run('toggle')
  assert(vim.wait(45000, function() return created ~= nil end, 20), 'reloaded session timed out')
  assert(created.session_id, 'reloaded session failed')
  assert(config.acp_configs.session_cwd() == second, 'reload retained old workspace')
  require('agentic').destroy_session()
  print('PASS new sessions use current workspace after config reload')
end)
vim.fn.delete(root, 'rf')
if not ok then io.stderr:write(tostring(err) .. '\n'); vim.cmd.cquit(1) end
vim.cmd('qa!')
