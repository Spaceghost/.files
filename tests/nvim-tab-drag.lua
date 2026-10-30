-- Run: nvim --headless -u NONE -l tests/nvim-tab-drag.lua
local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
local pipe
local function lua(code, ...)
  return vim.rpcrequest(child, 'nvim_exec_lua', code, { ... })
end
local function wait_for(code)
  assert(vim.wait(2000, function() return lua(code) end, 10), 'timed out: ' .. code)
end
local function mouse(action, col)
  vim.rpcrequest(child, 'nvim_input_mouse', 'left', action, '', 0, 0, col)
  vim.wait(40)
end
local function col(label)
  return lua([[
    local label = ...
    local line = vim.api.nvim_eval_statusline(vim.o.tabline, { use_tabline = true }).str
    local first = assert(line:find(label, 1, true), 'missing tab ' .. label)
    return vim.fn.strdisplaywidth(line:sub(1, first - 1))
  ]], label)
end
local ok, err = pcall(function()
  local socket = lua([[
    vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
    vim.g.spaceghost_no_shell = true
    dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')
    vim.t.spaceghost_name = 'one'
    Spaceghost.shell.open('tabnew', { cmd = { 'sh', '-c', 'cat' } })
    vim.t.spaceghost_name = 'two'
    Spaceghost.shell.open('tabnew', { cmd = { 'sh', '-c', 'cat' } })
    vim.t.spaceghost_name = 'three'
    _G.original_tabs = vim.api.nvim_list_tabpages()
    return vim.fn.serverstart(...)
  ]], vim.env.TMPDIR .. '/tab-drag-test.sock')
  pipe = vim.uv.new_pipe(false)
  local connected, problem = false, nil
  pipe:connect(socket, function(e) connected, problem = true, e end)
  assert(vim.wait(2000, function() return connected end, 10), 'UI connection timed out')
  assert(not problem, problem)
  pipe:read_start(function() end)
  pipe:write(vim.mpack.encode({ 2, 'nvim_ui_attach', { 160, 35, { rgb = true, ext_linegrid = true } } }))
  wait_for('return #vim.api.nvim_list_uis() > 0 and vim.api.nvim_get_mode().mode == "t"')

  -- Drag a terminal tab left across two tabs, then right again.
  mouse('press', col('three'))
  mouse('drag', col('one'))
  mouse('release', col('three'))
  wait_for('return vim.api.nvim_list_tabpages()[1] == original_tabs[3]')
  assert(lua('return vim.api.nvim_get_current_tabpage() == original_tabs[3]'), 'drag lost focus')
  vim.wait(550) -- Avoid interpreting the next press as a double-click.
  mouse('press', col('three'))
  mouse('drag', col('two'))
  mouse('release', col('three'))
  wait_for('return vim.deep_equal(vim.api.nvim_list_tabpages(), original_tabs)')

  -- Releasing clears the gesture: a stray drag must not reorder anything.
  mouse('drag', col('one'))
  assert(lua('return vim.deep_equal(vim.api.nvim_list_tabpages(), original_tabs)'), 'release left a stale drag')
  lua('Spaceghost.deck.reload()')
  vim.wait(550)
  mouse('press', col('three'))
  mouse('drag', col('one'))
  mouse('release', col('three'))
  wait_for('return vim.api.nvim_list_tabpages()[1] == original_tabs[3]')
  assert(lua('return #vim.api.nvim_list_tabpages() == 3'), 'drag opened or closed a tab')
end)
if pipe then pipe:read_stop(); pipe:close() end
vim.fn.jobstop(child)
assert(ok, err)
print('PASS real UI tab dragging left/right, release, terminal input and reload')
vim.cmd('qa!')
