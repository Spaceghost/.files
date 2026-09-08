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
vim.cmd.colorscheme("habamax")
vim.api.nvim_set_hl(0, "Normal", { bg = "#13091f", fg = "#eaddf5" })
vim.api.nvim_set_hl(0, "NormalFloat", { bg = "#1d0d2d", fg = "#eaddf5" })
vim.api.nvim_set_hl(0, "Visual", { bg = "#542476", fg = "#fff7ff" })
vim.api.nvim_set_hl(0, "CursorLine", { bg = "#211035" })
vim.api.nvim_set_hl(0, "LineNr", { fg = "#806991" })
vim.api.nvim_set_hl(0, "CursorLineNr", { fg = "#dca7ff", bold = true })
vim.keymap.set("n", "<leader>w", "<cmd>write<cr>", { silent = true })
vim.keymap.set("n", "<leader>q", "<cmd>quit<cr>", { silent = true })
