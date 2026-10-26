-- Real embedded UI regression: the cockpit prefix opens a prompt ready to type.
-- Run from repo root: nvim --headless -u NONE -l tests/nvim-agentic-terminal.lua
local config = vim.fn.getcwd() .. '/.config/nvim'
local root = vim.fn.tempname()
vim.fn.mkdir(root, 'p')
local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
local function lua(code, ...)
  return vim.rpcrequest(child, 'nvim_exec_lua', code, { ... })
end
local function wait_for(code)
  assert(vim.wait(45000, function() return lua(code) end, 20), 'timed out: ' .. code)
end
local ok, err = pcall(function()
  lua([[
    local config, root = ...
    vim.g.spaceghost_no_shell = true
    vim.opt.runtimepath:prepend(config)
    dofile(config .. '/init.lua')
    vim.o.columns = 160
    vim.o.lines = 48
    require('spaceghost.shell').open(nil, { cmd = { 'cat' }, cwd = root })
  ]], config, root)
  wait_for("return vim.api.nvim_get_mode().mode == 't'")
  vim.rpcrequest(child, 'nvim_input', '<C-\\>i')
  wait_for("return vim.bo.filetype == 'AgenticInput' and vim.api.nvim_get_mode().mode == 'i'")
  assert(lua("return require('agentic.config').acp_configs.session_cwd()") == root, 'shell workspace lost')
  vim.rpcrequest(child, 'nvim_input', 'hello')
  wait_for("return table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\\n'):find('hello', 1, true) ~= nil")
  print('PASS cockpit prefix opens native Codex input ready to type, in shell workspace')
end)
vim.fn.jobstop(child)
vim.fn.delete(root, 'rf')
if not ok then io.stderr:write(tostring(err) .. '\n'); vim.cmd.cquit(1) end
vim.cmd('qa!')
