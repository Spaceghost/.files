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
assert(not ui.tabline():find('ui.plus_click', 1, true), 'plus appears with one tab')
reset(2)
local line = ui.tabline()
assert(line:find('ui.tab_click', 1, true), 'tabs have no click handler')
assert(line:find('ui.plus_click', 1, true), 'plus missing with two tabs')
assert(line:find('ui.empty_click', 1, true), 'empty area has no click handler')
local rendered = vim.api.nvim_eval_statusline(line, { use_tabline = true, maxwidth = 200 }).str
assert(rendered:find('+', 1, true), 'plus is not visible')

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

print('PASS tabline click targets and new-shell placement')
vim.cmd('qa!')
