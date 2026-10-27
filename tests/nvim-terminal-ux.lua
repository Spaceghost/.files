-- Run from the repository: nvim --headless -u NONE -l tests/nvim-terminal-ux.lua
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
vim.g.spaceghost_no_shell = true
dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')

local prompts = {}
vim.api.nvim_create_autocmd('TermRequest', {
  callback = function(ev)
    local sequence = type(ev.data) == 'table' and ev.data.sequence or ev.data
    if type(sequence) == 'string' then
      local mark = sequence:match('^\27%]133;([AB])')
      if mark then prompts[#prompts + 1] = mark end
    end
  end,
})

local buf = Spaceghost.shell.open('tabnew', { cmd = { 'zsh', '-i' } })
assert(vim.wait(3000, function() return vim.tbl_contains(prompts, 'A') end, 20),
  'zsh did not mark its prompt for Neovim')
assert(vim.bo[buf].scrollback >= 20000, 'terminal scrollback is too short')
vim.api.nvim_chan_send(vim.bo[buf].channel, 'printf "first command\\n"\n')
assert(vim.wait(3000, function() return vim.tbl_contains(prompts, 'B') and #prompts >= 3 end, 20),
  'zsh did not mark command execution and the next prompt')

vim.api.nvim_feedkeys(vim.keycode('<C-\\><C-n>'), 'xt', false)
assert(Spaceghost.ui.statusline():find('COPY', 1, true), 'terminal copy mode is not identified')
vim.api.nvim_win_set_cursor(0, { vim.api.nvim_buf_line_count(buf), 0 })
local before = vim.api.nvim_win_get_cursor(0)[1]
assert(vim.fn.maparg('<C-\\>u', 't') ~= '', 'previous prompt shortcut is not mapped')
Spaceghost.shell.previous_prompt()
assert(vim.wait(1000, function() return vim.api.nvim_win_get_cursor(0)[1] < before end, 20),
  'previous prompt shortcut did not move upward')

print('PASS prompt markers, scrollback, copy mode and prompt jump')
vim.cmd('qa!')
