vim.g.mapleader = " "
vim.opt.number = true
vim.opt.relativenumber = true
vim.opt.signcolumn = "yes"
vim.opt.cursorline = true
vim.opt.mouse = "a"
vim.opt.termguicolors = true
vim.opt.splitright = true
vim.opt.splitbelow = true
vim.opt.ignorecase = true
vim.opt.smartcase = true
vim.opt.updatetime = 250
vim.opt.timeoutlen = 400
vim.opt.clipboard = "unnamedplus"
vim.opt.list = true
vim.opt.listchars = { tab = "» ", trail = "·", extends = "›", precedes = "‹" }
vim.cmd.colorscheme("gruvbox-dark")
vim.keymap.set("n", "<leader>w", "<cmd>write<cr>", { silent = true })
vim.keymap.set("n", "<leader>q", "<cmd>quit<cr>", { silent = true })
