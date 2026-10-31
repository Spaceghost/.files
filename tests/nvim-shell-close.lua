-- Run: nvim --headless -u NONE -l tests/nvim-shell-close.lua
local runtime = vim.fn.getcwd() .. '/.config/nvim'

local function scenario(name, code)
  local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
  local function lua(source, ...)
    return vim.rpcrequest(child, 'nvim_exec_lua', source, { ... })
  end
  local ok, err = pcall(function()
    lua([[
      vim.opt.runtimepath:prepend(...)
      vim.g.spaceghost_no_shell = true
      shell = require('spaceghost.shell')
      shell.setup()
      root = shell.open(nil, { root = true, cmd = { 'sh' } })
    ]], runtime)
    lua(code)
    assert(vim.wait(2000, function()
      return lua('return not vim.api.nvim_buf_is_valid(root)')
    end, 10), 'startup shell did not close')
    lua([[
      assert(#vim.api.nvim_list_tabpages() == expected_tabs, 'wrong number of remaining tabs')
      assert(#vim.api.nvim_list_wins() == 1, 'closed shell left an empty pane')
      if survivor then
        assert(vim.api.nvim_get_current_buf() == survivor, 'surviving shell lost focus')
        assert(vim.fn.jobwait({ vim.bo[survivor].channel }, 0)[1] == -1, 'surviving shell stopped')
      end
      if detached then
        assert(vim.api.nvim_buf_is_valid(detached), 'detached shell was deleted')
        assert(vim.fn.jobwait({ vim.bo[detached].channel }, 0)[1] == -1, 'detached shell stopped')
      end
    ]])
  end)
  pcall(lua, "vim.cmd('qa!')")
  pcall(vim.fn.jobstop, child)
  assert(ok, name .. ': ' .. tostring(err))
  print('PASS ' .. name)
end

scenario('exit first shell preserves another tab', [[
  survivor = shell.open('$tabnew', { cmd = { 'sh' } })
  expected_tabs = 1
  vim.api.nvim_chan_send(vim.bo[root].channel, 'exit\n')
]])

scenario('close first pane preserves another split', [[
  survivor = shell.open('vnew', { cmd = { 'sh' } })
  vim.api.nvim_set_current_win(vim.fn.win_findbuf(root)[1])
  expected_tabs = 1
  require('spaceghost.keys').close_pane()
]])

scenario('closing first shell keeps detached work alive', [[
  detached = shell.open('$tabnew', { cmd = { 'sh' } })
  vim.cmd('tabclose')
  expected_tabs = 1
  vim.api.nvim_chan_send(vim.bo[root].channel, 'exit\n')
]])

scenario('shared server survives its last shell closing', [[
  shell.is_server = true
  expected_tabs = 1
  require('spaceghost.keys').close_pane()
]])

vim.cmd('qa!')
