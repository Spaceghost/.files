-- Run from the repository: nvim --headless -u NONE -l tests/nvim-navigation.lua
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
vim.g.spaceghost_no_shell = true
local shell = require('spaceghost.shell')
local keys = require('spaceghost.keys')
shell.setup()
keys.setup()

local failures = 0
local function test(name, fn)
  local ok, err = pcall(fn)
  if not ok then
    failures = failures + 1
    io.stderr:write('FAIL ' .. name .. ': ' .. tostring(err) .. '\n')
  else print('PASS ' .. name) end
end

test('previous pane crosses tabs and toggles back', function()
  local first = vim.api.nvim_get_current_win()
  vim.cmd.tabnew()
  local second = vim.api.nvim_get_current_win()
  keys.previous_pane()
  assert(vim.api.nvim_get_current_win() == first, 'did not return across tabs')
  keys.previous_pane()
  assert(vim.api.nvim_get_current_win() == second, 'did not toggle back')
end)

test('tab navigation wraps in both directions', function()
  vim.cmd.tabfirst()
  keys.focus_tab(-1)
  assert(vim.fn.tabpagenr() == vim.fn.tabpagenr('$'), 'previous did not wrap')
  keys.focus_tab(1)
  assert(vim.fn.tabpagenr() == 1, 'next did not wrap')
end)

test('picker includes every pane and identifies remote hosts', function()
  vim.cmd('tabonly!')
  for _ = 1, 29 do vim.cmd.tabnew() end
  vim.b.spaceghost_attach = 'test-host'
  local deck = require('spaceghost.deck')
  deck.choose_window()
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  assert(#lines == 30, 'picker lost panes: ' .. #lines)
  assert(table.concat(lines, '\n'):find('@test-host', 1, true), 'host missing')
  vim.api.nvim_win_set_cursor(0, { 1, 0 })
  vim.api.nvim_feedkeys(vim.keycode('<CR>'), 'xt', false)
  vim.wait(100, function() return vim.fn.tabpagenr() == 1 end)
  assert(vim.fn.tabpagenr() == 1, 'selection did not focus its tab')
end)

test('picker cancel restores focus without polluting previous pane', function()
  local first = vim.api.nvim_get_current_win()
  vim.cmd.tabnext()
  local second = vim.api.nvim_get_current_win()
  require('spaceghost.deck').choose_window()
  vim.api.nvim_feedkeys(vim.keycode('<Esc>'), 'xt', false)
  assert(vim.api.nvim_get_current_win() == second, 'cancel lost focus')
  keys.previous_pane()
  assert(vim.api.nvim_get_current_win() == first, 'picker polluted focus history')
end)

test('closed panes are skipped and reload preserves focus history', function()
  vim.cmd('tabonly!')
  local first = vim.api.nvim_get_current_win()
  vim.cmd.tabnew()
  local second = vim.api.nvim_get_current_win()
  vim.cmd.tabnew()
  local third = vim.api.nvim_get_current_win()
  vim.api.nvim_win_close(second, true)
  package.loaded['spaceghost.keys'] = nil
  keys = require('spaceghost.keys')
  keys.setup()
  keys.previous_pane()
  assert(vim.api.nvim_get_current_win() == first, 'closed pane blocked history')
  keys.previous_pane()
  assert(vim.api.nvim_get_current_win() == third, 'reload lost recent pane')
end)

test('direct shortcuts and picker work from running terminal input', function()
  local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
  local function lua(code, ...) return vim.rpcrequest(child, 'nvim_exec_lua', code, { ... }) end
  local function input(key) vim.rpcrequest(child, 'nvim_input', key) end
  local function wait_for(code)
    assert(vim.wait(2000, function() return lua(code) end, 10), 'timed out: ' .. code)
  end
  local ok, err = pcall(function()
    lua([[
      vim.opt.runtimepath:prepend(...)
      vim.g.spaceghost_no_shell = true
      local shell = require('spaceghost.shell')
      shell.setup()
      require('spaceghost.keys').setup()
      local cmd = { 'sh', '-c', 'while IFS= read -r line; do printf "received:%s\\n" "$line"; done' }
      shell.open(nil, { cmd = cmd })
      vim.b.term_title = 'test-host'
      vim.t.spaceghost_name = 'backend'
      shell.open('tabnew', { cmd = cmd })
    ]], vim.fn.getcwd() .. '/.config/nvim')
    wait_for("return vim.api.nvim_get_mode().mode == 't'")
    input('<M-[>')
    wait_for("return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
    input('<M-2>')
    wait_for("return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
    input('<F2>')
    wait_for("return vim.bo.buftype == 'nofile' and vim.api.nvim_get_mode().mode == 'n'")
    input('/test-host<CR><CR>')
    wait_for("return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
    input('<M-o>')
    wait_for("return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
    lua([[require('spaceghost.shell').open('belowright vnew', {
      cmd = {'sh', '-c', 'while IFS= read -r line; do printf "received:%s\\n" "$line"; done'}
    })]])
    local right = lua('return vim.api.nvim_get_current_win()')
    input([[<C-\>h]])
    wait_for('return vim.api.nvim_get_current_win() ~= ' .. right .. " and vim.api.nvim_get_mode().mode == 't'")
    input([[<C-\>l]])
    wait_for('return vim.api.nvim_get_current_win() == ' .. right .. " and vim.api.nvim_get_mode().mode == 't'")
    input('<F4>')
    wait_for("return vim.bo.buftype == 'nofile' and vim.api.nvim_get_mode().mode == 'n'")
    input('<Esc>')
    wait_for("return vim.bo.buftype == 'terminal' and vim.api.nvim_get_mode().mode == 't'")
    input('navigation-test<CR>')
    wait_for([[return table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\n'):find('received:navigation%-test') ~= nil]])
    input([[<C-\>p]])
    wait_for("return vim.fn.tabpagenr() == 1 and vim.api.nvim_get_mode().mode == 't'")
    input([[<C-\>n]])
    wait_for("return vim.fn.tabpagenr() == 2 and vim.api.nvim_get_mode().mode == 't'")
  end)
  vim.fn.jobstop(child)
  assert(ok, err)
end)

test('Alt arrows reach terminal apps after upgrading a running config', function()
  local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
  local function lua(code, ...) return vim.rpcrequest(child, 'nvim_exec_lua', code, { ... }) end
  local ok, err = pcall(function()
    lua([[
      vim.opt.runtimepath:prepend(...)
      vim.g.spaceghost_no_shell = true
      local shell = require('spaceghost.shell')
      local keys = require('spaceghost.keys')
      shell.setup()
      -- Reproduce the previous config's binding before reloading setup.
      vim.keymap.set({'n', 't'}, '<M-Up>', function() keys.focus_pane('k') end)
      keys.setup()
      shell.open(nil, {cmd = {'sh', '-c', 'cat'}})
      shell.open('belowright new', {cmd = {'python3', '-u', '-c', [=[
import os, tty
tty.setraw(0)
os.write(1, b'KEYS-READY\r\n')
while True:
    data = os.read(0, 64)
    os.write(1, b'KEY:' + data.hex().encode() + b'\r\n')
]=]}})
    ]], vim.fn.getcwd() .. '/.config/nvim')
    local win = lua('return vim.api.nvim_get_current_win()')
    local function received(text)
      return lua("return table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\\n'):find(..., 1, true) ~= nil", text)
    end
    assert(vim.wait(2000, function() return received('KEYS-READY') end, 10), 'key reader did not start')
    for _, key in ipairs({ {'Up', '1b5b313b3341'}, {'Down', '1b5b313b3342'}, {'Left', '1b5b313b3344'}, {'Right', '1b5b313b3343'} }) do
      vim.rpcrequest(child, 'nvim_input', '<M-' .. key[1] .. '>')
      assert(vim.wait(2000, function() return received('KEY:' .. key[2]) end, 10), 'Alt-' .. key[1] .. ' was intercepted')
      assert(lua('return vim.api.nvim_get_current_win()') == win, 'Alt-arrow changed pane')
    end
  end)
  vim.fn.jobstop(child)
  assert(ok, err)
end)

test('terminal follows smallest client and grows after resize or detach', function()
  local child = vim.fn.jobstart({ vim.v.progpath, '--embed', '--headless', '-u', 'NONE' }, { rpc = true })
  local clients = {}
  local function lua(code, ...) return vim.rpcrequest(child, 'nvim_exec_lua', code, { ... }) end
  -- Drain redraw notifications: these clients display nothing and only report
  -- their size. Neovim's own RPC client cannot act as a remote UI for itself.
  local function attach(socket, width, height)
    local pipe = vim.uv.new_pipe(false)
    clients[#clients + 1] = pipe
    local connected, problem = false, nil
    pipe:connect(socket, function(err) connected, problem = true, err end)
    assert(vim.wait(2000, function() return connected end, 10), 'UI connection timed out')
    assert(not problem, problem)
    pipe:read_start(function() end)
    pipe:write(vim.mpack.encode({ 2, 'nvim_ui_attach', { width, height, { rgb = true, ext_linegrid = true } } }))
    return pipe
  end
  local function fits(width, height)
    assert(vim.wait(2000, function()
      local state = lua([[return {vim.o.columns, vim.o.lines,
        vim.api.nvim_win_get_width(0), vim.api.nvim_win_get_height(0),
        vim.api.nvim_get_chan_info(vim.bo.channel).pty} ]])
      if state[1] ~= width or state[2] ~= height then return false end
      if state[3] ~= width or state[4] ~= height - 2 then return false end
      local size = vim.fn.system({ 'python3', '-c', [[
import fcntl, termios, struct, sys
with open(sys.argv[1], 'rb', buffering=0) as pty:
    rows, cols, _, _ = struct.unpack('HHHH', fcntl.ioctl(pty, termios.TIOCGWINSZ, b'\0'*8))
    print(str(cols)+'x'+str(rows))
]], state[5] }):gsub('%s+$', '')
      return size == state[3] .. 'x' .. state[4]
    end, 20), 'terminal did not fill pane at client size ' .. width .. 'x' .. height)
  end
  local ok, err = pcall(function()
    local socket = lua([[
      vim.opt.runtimepath:prepend(...)
      vim.g.spaceghost_no_shell = true
      dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')
      Spaceghost.shell.open(nil, { cmd = {'sh', '-c', 'cat'} })
      return vim.fn.serverstart()
    ]], vim.fn.getcwd() .. '/.config/nvim')
    attach(socket, 160, 50)
    fits(160, 50)
    local second = attach(socket, 90, 30)
    fits(90, 30)
    second:write(vim.mpack.encode({ 2, 'nvim_ui_try_resize', { 120, 40 } }))
    fits(120, 40)
    second:write(vim.mpack.encode({ 2, 'nvim_ui_detach', {} }))
    fits(160, 50)
  end)
  for _, client in ipairs(clients) do client:read_stop(); client:close() end
  vim.fn.jobstop(child)
  assert(ok, err)
end)

test('shell fills a pane that previously displayed a file', function()
  vim.cmd('tabonly!')
  vim.wo.foldcolumn = '2'
  vim.wo.winbar = 'file breadcrumb'
  local buf = shell.open('tabnew', { cmd = { 'sh', '-c', 'cat' } })
  assert(vim.fn.getwininfo(vim.api.nvim_get_current_win())[1].textoff == 0, 'file gutters shrink a new terminal')
  assert(vim.wo.winbar == '', 'file winbar shrinks a new terminal')
  vim.cmd.stopinsert()
  vim.cmd.enew()
  vim.wo.number = true
  vim.wo.relativenumber = true
  vim.wo.signcolumn = 'yes:2'
  vim.wo.foldcolumn = '2'
  vim.wo.winbar = 'file breadcrumb'
  vim.api.nvim_win_set_buf(0, buf)
  assert(vim.fn.getwininfo(vim.api.nvim_get_current_win())[1].textoff == 0, 'file gutters shrink the terminal')
  assert(vim.wo.winbar == '', 'file winbar shrinks the terminal')
end)

vim.cmd(failures > 0 and 'cquit 1' or 'qa!')
