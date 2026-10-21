-- Run: nvim --headless -u NONE -l tests/nvim-nested.lua
-- A real --remote-ui runs inside an outer PTY; neither layer is mocked.
local config = vim.fn.getcwd() .. '/.config/nvim'
local children, failures = {}, 0
local function spawn()
  local channel = vim.fn.jobstart({ vim.v.progpath, '--headless', '--embed', '-u', 'NONE' }, { rpc = true })
  children[#children + 1] = channel
  vim.rpcrequest(channel, 'nvim_exec_lua', [[
    vim.opt.runtimepath:prepend(...)
    vim.g.spaceghost_no_shell = true
    dofile((...) .. '/init.lua')
  ]], { config })
  return channel
end
local function lua(channel, code, ...)
  return vim.rpcrequest(channel, 'nvim_exec_lua', code, { ... })
end
local function input(channel, key) vim.rpcrequest(channel, 'nvim_input', key) end
local function wait_for(channel, code)
  assert(vim.wait(3000, function() return lua(channel, code) end, 10), 'timed out: ' .. code)
end
local function test(name, fn)
  local ok, err = pcall(fn)
  if ok then io.stdout:write('PASS ' .. name .. '\n')
  else failures = failures + 1; io.stderr:write('FAIL ' .. name .. ': ' .. tostring(err) .. '\n') end
end

local inner, outer = spawn(), spawn()
local socket = lua(inner, [[
  local shell = Spaceghost.shell
  shell.open(nil, { cmd = {'sh', '-c', 'cat'} })
  vim.t.spaceghost_name = 'remote-one'
  shell.open('tabnew', { cmd = {'sh', '-c', 'cat'} })
  vim.t.spaceghost_name = 'remote-two'
  return vim.fn.serverstart()
]])
local host_win = lua(outer, [[
  Spaceghost.shell.open(nil, { cmd = {'sh', '-c', 'cat'} })
  Spaceghost.shell.open('tabnew', { cmd = {vim.v.progpath, '--server', ..., '--remote-ui'} })
  vim.b.spaceghost_attach = 'test-host'
  return vim.api.nvim_get_current_win()
]], socket)
wait_for(inner, "return #vim.api.nvim_list_uis() == 1 and vim.api.nvim_get_mode().mode == 't'")
wait_for(outer, "return vim.api.nvim_get_mode().mode == 't'")

test('remote mode routes tab shortcuts and F2 through the PTY', function()
  input(outer, '<C-]>')
  wait_for(outer, 'return vim.b.spaceghost_remote_keys == true')
  input(outer, '<M-1>')
  wait_for(inner, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  assert(lua(outer, 'return vim.fn.tabpagenr()') == 2, 'outer tab changed')
  input(outer, '<M-]>')
  wait_for(inner, "return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<M-[>')
  wait_for(inner, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<C-PageDown>')
  wait_for(inner, "return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<M-o>')
  wait_for(inner, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<F2>')
  wait_for(inner, "return vim.bo.buftype == 'nofile' and vim.api.nvim_get_mode().mode == 'n'")
  assert(lua(outer, 'return vim.bo.buftype') == 'terminal', 'outer intercepted the picker')
  input(outer, '/remote-two<CR><CR>')
  wait_for(inner, "return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
  lua(inner, "Spaceghost.shell.open('belowright vnew', {cmd = {'sh', '-c', 'cat'}})")
  local right = lua(inner, 'return vim.api.nvim_get_current_win()')
  input(outer, '<M-Left>')
  wait_for(inner, 'return vim.api.nvim_get_current_win() ~= ' .. right)
  input(outer, '<M-Right>')
  wait_for(inner, 'return vim.api.nvim_get_current_win() == ' .. right)
  input(outer, '<F4>')
  wait_for(inner, "return vim.bo.buftype == 'nofile' and vim.api.nvim_get_mode().mode == 'n'")
  input(outer, '<Esc>')
  wait_for(inner, "return vim.bo.buftype == 'terminal' and vim.api.nvim_get_mode().mode == 't'")
  lua(outer, [[
    package.loaded['spaceghost.keys'] = nil
    Spaceghost.keys = require('spaceghost.keys')
    Spaceghost.keys.setup()
  ]])
  input(outer, '<M-1>')
  wait_for(inner, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<M-2>')
  wait_for(inner, "return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<C-]>')
  wait_for(outer, 'return vim.b.spaceghost_remote_keys == false')
  input(outer, '<M-1>')
  wait_for(outer, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  assert(lua(inner, 'return vim.fn.tabpagenr()') == 2, 'local navigation changed remote tab')
end)

-- Reset both layers even when an earlier assertion failed.
lua(outer, 'vim.api.nvim_set_current_win(...); Spaceghost.shell.remote_keys(nil, false)', host_win)
lua(inner, "if vim.bo.buftype == 'nofile' then vim.api.nvim_win_close(0, true) end")
test('local picker opens the selected hosts own tab picker', function()
  input(outer, '<M-1>')
  wait_for(outer, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<F2>')
  wait_for(outer, "return vim.bo.buftype == 'nofile' and vim.api.nvim_get_mode().mode == 'n'")
  input(outer, '/test-host<CR><CR>')
  wait_for(inner, "return vim.bo.buftype == 'nofile' and vim.api.nvim_get_mode().mode == 'n'")
  assert(lua(outer, 'return vim.b.spaceghost_remote_keys') == true, 'host navigation not enabled')
  input(outer, '/remote-one<CR><CR>')
  wait_for(inner, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
  input(outer, '<C-]>')
  input(outer, '<M-1>')
  wait_for(outer, "return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
end)

for i = #children, 1, -1 do vim.fn.jobstop(children[i]) end
vim.cmd(failures > 0 and 'cquit 1' or 'qa!')
