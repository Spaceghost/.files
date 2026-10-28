-- Run from the repository: nvim --headless -u NONE -l tests/nvim-tabline.lua
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
vim.g.spaceghost_no_shell = true
dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')

local ui = Spaceghost.ui
local function tabs() return vim.api.nvim_list_tabpages() end
local function reset(count)
  if #tabs() > 1 then vim.cmd('tabonly!') end
  for _ = 2, count do vim.cmd.tabnew() end
end

reset(1)
local single = ui.tabline()
assert(single:find('ui.plus_click', 1, true), 'new-shell button missing with one tab')
local single_rendered = vim.api.nvim_eval_statusline(single, { use_tabline = true, maxwidth = 200 }).str
assert(single_rendered:find('', 1, true), 'terminal icon missing with one tab')
ui.plus_click(0, 1, 'l', ' ')
ui.plus_release()
vim.wait(20)
assert(#tabs() == 2 and vim.api.nvim_get_current_tabpage() == tabs()[2]
  and vim.bo.buftype == 'terminal', 'single-tab button did not open a shell on the right')
reset(2)
local line = ui.tabline()
assert(line:find('ui.tab_click', 1, true), 'tabs have no click handler')
assert(line:find('ui.plus_click', 1, true), 'new-shell button missing with two tabs')
assert(line:find('ui.empty_click', 1, true), 'empty area has no click handler')
local rendered = vim.api.nvim_eval_statusline(line, { use_tabline = true, maxwidth = 200 }).str
assert(rendered:find('', 1, true), 'terminal icon is not visible')

reset(3)
local originals = tabs()
ui.tab_click(1, 1, 'l', ' ')
assert(vim.api.nvim_get_current_tabpage() == originals[1], 'single click did not select tab')
ui.tab_click(2, 2, 'l', ' ')
local ordered = tabs()
assert(#ordered == 4 and ordered[1] == originals[1] and ordered[2] == originals[2]
  and ordered[4] == originals[3] and ordered[3] == vim.api.nvim_get_current_tabpage(),
  'double click did not open shell directly after clicked tab')
assert(vim.bo.buftype == 'terminal', 'double click did not open a shell')

ui.plus_click(0, 1, 'l', ' ')
ui.plus_release()
vim.wait(20)
assert(vim.api.nvim_get_current_tabpage() == tabs()[#tabs()] and #tabs() == 5,
  'plus did not open shell on far right')
ui.empty_click(0, 1, 'l', ' ')
assert(#tabs() == 5, 'single click on empty area opened a tab')
ui.empty_click(0, 2, 'l', ' ')
assert(vim.api.nvim_get_current_tabpage() == tabs()[#tabs()] and #tabs() == 6,
  'double click on empty area did not open shell on far right')
local first = tabs()[1]
ui.tab_click(1, 1, 'm', ' ')
assert(#tabs() == 5 and tabs()[1] ~= first, 'middle click did not close its tab')

local hostname = vim.fn.hostname
for _, current in ipairs({ 'alienware', 'fedora', 'bak' }) do
  vim.fn.hostname = function() return current end
  ui.plus_click(0, 1, 'r', ' ')
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  assert(lines[1]:find('Local shell tab', 1, true), 'local option is not first')
  local menu = table.concat(lines, '\n')
  for _, host in ipairs({ 'bak', 'fedora', 'alienware' }) do
    assert((menu:find('  ' .. host .. '\n', 1, true) ~= nil) == (host ~= current),
      'host list is wrong on ' .. current .. ': ' .. host)
  end
  vim.api.nvim_win_close(0, true)
end
vim.fn.hostname = hostname

local target = tabs()[2]
ui.tab_click(2, 1, 'r', ' ')
local actions = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), '\n')
assert(actions:find('Detach tab', 1, true) and actions:find('Close tab', 1, true),
  'tab context menu is missing detach or close')
vim.api.nvim_win_close(0, true)
local target_buf = vim.api.nvim_win_get_buf(vim.api.nvim_tabpage_get_win(target))
ui.detach_tab(target)
assert(not vim.api.nvim_tabpage_is_valid(target) and vim.api.nvim_buf_is_valid(target_buf)
  and #vim.fn.win_findbuf(target_buf) == 0, 'detach did not preserve a hidden buffer')
local select = vim.ui.select
vim.ui.select = function(items, _, callback) callback(items[1]) end
ui.reopen_detached()
vim.ui.select = select
assert(#vim.fn.win_findbuf(target_buf) > 0, 'detached tab did not reopen')
ui.close_tab(vim.api.nvim_get_current_tabpage())
assert(not vim.api.nvim_buf_is_valid(target_buf), 'close tab did not stop its shell')

print('PASS tabline menus, host list, detach, close and new-shell placement')
vim.cmd('qa!')
