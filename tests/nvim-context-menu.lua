-- Run from the repository: nvim --headless -u NONE -l tests/nvim-context-menu.lua
-- A real remote UI is needed: tabline mouse callbacks do not fire headless.
local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
local pipe
local function lua(code, ...)
  return vim.rpcrequest(child, 'nvim_exec_lua', code, { ... })
end
local function mouse(button, action, row, col)
  vim.rpcrequest(child, 'nvim_input_mouse', button, action, '', 1, row, col)
end
local function wait_for(code)
  assert(vim.wait(2000, function() return lua(code) end, 10), 'timed out: ' .. code)
end
local function target_tab_col()
  local line = lua([[return vim.api.nvim_eval_statusline(vim.o.tabline, { use_tabline = true }).str]])
  local start = assert(line:find('2 / target', 1, true), 'target tab is missing')
  return start - 1
end

local ok, err = pcall(function()
  local socket = lua([[
    local runtime, path = ...
    vim.opt.runtimepath:prepend(runtime)
    vim.g.spaceghost_no_shell = true
    dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')
    Spaceghost.shell.open('tabnew', { cmd = { 'sh', '-c', 'cat' } })
    vim.t.spaceghost_name = 'target'
    return vim.fn.serverstart(path)
  ]], vim.fn.getcwd() .. '/.config/nvim', vim.env.TMPDIR .. '/context-menu-test.sock')
  pipe = vim.uv.new_pipe(false)
  local connected, problem = false, nil
  pipe:connect(socket, function(e) connected, problem = true, e end)
  assert(vim.wait(2000, function() return connected end, 10), 'UI connection timed out')
  assert(not problem, problem)
  pipe:read_start(function() end)
  pipe:write(vim.mpack.encode({ 2, 'nvim_ui_attach', { 120, 35, { rgb = true, ext_linegrid = true } } }))
  wait_for('return #vim.api.nvim_list_uis() > 0 and vim.api.nvim_get_mode().mode == "t"')

  -- Right-click the second tab while the shell owns terminal input.
  local tab_col = target_tab_col()
  mouse('right', 'press', 0, tab_col)
  mouse('right', 'release', 0, tab_col)
  wait_for("return vim.bo.buftype == 'nofile'")
  assert(lua("return vim.api.nvim_get_mode().mode") == 'n',
    'tab menu entered insert mode after a terminal right-click')
  vim.rpcrequest(child, 'nvim_input', 'd')
  wait_for('return #vim.api.nvim_list_tabpages() == 1')

  -- The same menu must accept a pointer selection after reopening a shell tab.
  lua([[Spaceghost.shell.open('tabnew', { cmd = { 'sh', '-c', 'cat' } }); vim.t.spaceghost_name = 'target']])
  wait_for("return vim.api.nvim_get_mode().mode == 't'")
  lua('vim.cmd.redrawtabline()')
  vim.wait(50)
  tab_col = target_tab_col()
  mouse('right', 'press', 0, tab_col)
  mouse('right', 'release', 0, tab_col)
  wait_for("return vim.bo.buftype == 'nofile'")
  local position = lua([[local c = vim.api.nvim_win_get_config(0); return { c.row, c.col }]])
  vim.rpcrequest(child, 'nvim_input_mouse', 'left', 'press', '', 0, position[1] + 1, position[2] + 4)
  vim.rpcrequest(child, 'nvim_input_mouse', 'left', 'release', '', 0, position[1] + 1, position[2] + 4)
  wait_for('return #vim.api.nvim_list_tabpages() == 1')

  -- The plus button uses the same floating menu from terminal input.
  local plus_col = lua([[Spaceghost.ui.tabline(); return Spaceghost.ui.plus_col + 1]])
  mouse('right', 'press', 0, plus_col)
  mouse('right', 'release', 0, plus_col)
  wait_for("return vim.bo.buftype == 'nofile'")
  assert(lua("return vim.api.nvim_get_mode().mode") == 'n',
    'new-tab context menu entered insert mode')
  vim.rpcrequest(child, 'nvim_input', 'c')
  wait_for("return #vim.api.nvim_list_tabpages() == 2 and vim.bo.buftype == 'terminal'")
end)
if pipe then pipe:read_stop(); pipe:close() end
vim.fn.jobstop(child)
assert(ok, err)
print('PASS terminal tab context menus accept keyboard and mouse actions')
vim.cmd('qa!')
