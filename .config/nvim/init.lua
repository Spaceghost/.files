local vimrc = vim.fn.expand("~/.vimrc")
if vim.fn.filereadable(vimrc) == 1 then
  vim.cmd.source(vimrc)
end

vim.opt.termguicolors = true
vim.opt.inccommand = "split"
vim.opt.signcolumn = "yes"
vim.opt.undofile = true
