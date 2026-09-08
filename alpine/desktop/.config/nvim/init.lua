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

-- Chrome: a hand-rolled Gruvbox statusline and winbar. No plugin manager, no plugins.
vim.opt.laststatus = 3
vim.opt.showmode = false
vim.opt.fillchars = {
    vert = "▏", vertleft = "▏", vertright = "▏", verthoriz = "▏",
    horiz = "─", horizup = "─", horizdown = "─",
    eob = " ", stl = " ", stlnc = " ", fold = " ", diff = "╱",
}

local palette = {
    bg = "#282828", hard = "#1d2021", soft = "#32302f", bg1 = "#3c3836", bg2 = "#504945",
    fg = "#ebdbb2", bright = "#fbf1c7", muted = "#928374", red = "#fb4934", green = "#b8bb26",
    yellow = "#fabd2f", blue = "#83a598", purple = "#d3869b", aqua = "#8ec07c", orange = "#fe8019",
}

local function chrome_highlights()
    local set = vim.api.nvim_set_hl
    set(0, "StatusLine", { fg = palette.fg, bg = palette.bg1 })
    set(0, "StatusLineNC", { fg = palette.muted, bg = palette.bg1 })
    set(0, "WinBar", { fg = palette.fg, bg = palette.bg })
    set(0, "WinBarNC", { fg = palette.muted, bg = palette.bg })
    set(0, "WinSeparator", { fg = palette.bg2, bg = palette.bg })
    local modes = {
        Normal = palette.yellow, Insert = palette.green, Visual = palette.purple,
        Replace = palette.red, Command = palette.aqua, Terminal = palette.blue, Other = palette.orange,
    }
    for name, color in pairs(modes) do
        set(0, "OldbookMode" .. name, { fg = palette.hard, bg = color, bold = true })
        set(0, "OldbookMode" .. name .. "Edge", { fg = color, bg = palette.bg2 })
    end
    set(0, "OldbookFile", { fg = palette.bright, bg = palette.bg2, bold = true })
    set(0, "OldbookFileEdge", { fg = palette.bg2, bg = palette.bg1 })
    set(0, "OldbookModified", { fg = palette.orange, bg = palette.bg2, bold = true })
    set(0, "OldbookBranch", { fg = palette.purple, bg = palette.bg1 })
    set(0, "OldbookInfo", { fg = palette.muted, bg = palette.bg1 })
    set(0, "OldbookError", { fg = palette.red, bg = palette.bg1, bold = true })
    set(0, "OldbookWarn", { fg = palette.yellow, bg = palette.bg1, bold = true })
    set(0, "OldbookPosition", { fg = palette.hard, bg = palette.aqua, bold = true })
    set(0, "OldbookPositionEdge", { fg = palette.aqua, bg = palette.bg1 })
    set(0, "OldbookWinbarIcon", { fg = palette.yellow, bg = palette.bg })
    set(0, "OldbookWinbarModified", { fg = palette.orange, bg = palette.bg, bold = true })
end
chrome_highlights()
vim.api.nvim_create_autocmd("ColorScheme", { callback = chrome_highlights })

local mode_names = {
    n = { "NORMAL", "Normal" }, no = { "PENDING", "Other" }, nov = { "PENDING", "Other" },
    noV = { "PENDING", "Other" }, ["no\22"] = { "PENDING", "Other" }, niI = { "NORMAL", "Normal" },
    niR = { "NORMAL", "Normal" }, niV = { "NORMAL", "Normal" }, nt = { "NORMAL", "Normal" },
    v = { "VISUAL", "Visual" }, vs = { "VISUAL", "Visual" }, V = { "V-LINE", "Visual" },
    Vs = { "V-LINE", "Visual" }, ["\22"] = { "V-BLOCK", "Visual" }, ["\22s"] = { "V-BLOCK", "Visual" },
    s = { "SELECT", "Visual" }, S = { "S-LINE", "Visual" }, ["\19"] = { "S-BLOCK", "Visual" },
    i = { "INSERT", "Insert" }, ic = { "INSERT", "Insert" }, ix = { "INSERT", "Insert" },
    R = { "REPLACE", "Replace" }, Rc = { "REPLACE", "Replace" }, Rx = { "REPLACE", "Replace" },
    Rv = { "V-REPLACE", "Replace" }, Rvc = { "V-REPLACE", "Replace" }, Rvx = { "V-REPLACE", "Replace" },
    c = { "COMMAND", "Command" }, cv = { "EX", "Command" }, ce = { "EX", "Command" },
    r = { "PROMPT", "Other" }, rm = { "MORE", "Other" }, ["r?"] = { "CONFIRM", "Other" },
    ["!"] = { "SHELL", "Other" }, t = { "TERMINAL", "Terminal" },
}

-- The branch is read from the checkout on disk, cached per directory, and
-- refreshed at most every thirty seconds so the statusline never spawns work.
local branch_cache = {}
local function checkout_branch()
    local directory = vim.fn.expand("%:p:h")
    if directory == "" then directory = vim.fn.getcwd() end
    local cached = branch_cache[directory]
    local now = vim.uv.now()
    if cached and now - cached.at < 30000 then return cached.branch end
    local branch = ""
    local fossil = vim.fs.find(".fslckout", { path = directory, upward = true })[1]
    local git = vim.fs.find(".git", { path = directory, upward = true })[1]
    if fossil then
        branch_cache[directory] = { branch = cached and cached.branch or "", at = now }
        vim.system({ "fossil", "branch", "current" }, { cwd = vim.fs.dirname(fossil), text = true },
            function(result)
                local name = result.code == 0 and vim.trim(result.stdout or "") or ""
                branch_cache[directory] = { branch = name ~= "" and ("󰜘 " .. name) or "", at = vim.uv.now() }
                vim.schedule(function() vim.cmd.redrawstatus() end)
            end)
        return branch_cache[directory].branch
    elseif git then
        local head = vim.fn.isdirectory(git) == 1 and (git .. "/HEAD") or nil
        if head and vim.fn.filereadable(head) == 1 then
            local line = vim.fn.readfile(head, "", 1)[1] or ""
            branch = line:match("ref: refs/heads/(.+)") or line:sub(1, 8)
            if branch ~= "" then branch = "󰘬 " .. branch end
        end
    end
    branch_cache[directory] = { branch = branch, at = now }
    return branch
end

local function diagnostics()
    if not vim.diagnostic.count then return "" end
    local counts = vim.diagnostic.count(0)
    local errors = counts[vim.diagnostic.severity.ERROR] or 0
    local warnings = counts[vim.diagnostic.severity.WARN] or 0
    local parts = {}
    if errors > 0 then parts[#parts + 1] = "%#OldbookError#󰅚 " .. errors end
    if warnings > 0 then parts[#parts + 1] = "%#OldbookWarn#󰀪 " .. warnings end
    return table.concat(parts, " ")
end

function _G.oldbook_statusline()
    local mode = mode_names[vim.api.nvim_get_mode().mode] or { "OTHER", "Other" }
    local name = vim.fn.expand("%:t")
    if name == "" then name = "[No Name]" end
    local modified = vim.bo.modified and "%#OldbookModified# ●" or ""
    local readonly = (vim.bo.readonly or not vim.bo.modifiable) and " 󰌾" or ""
    local filetype = vim.bo.filetype ~= "" and vim.bo.filetype or "text"
    local branch = checkout_branch()
    local left = table.concat({
        "%#OldbookMode" .. mode[2] .. "# " .. mode[1] .. " ",
        "%#OldbookMode" .. mode[2] .. "Edge#",
        "%#OldbookFile# " .. name .. readonly, modified, "%#OldbookFile# ",
        "%#OldbookFileEdge#",
        branch ~= "" and ("%#OldbookBranch# " .. branch .. " ") or "",
        " ", diagnostics(),
    })
    local right = table.concat({
        "%#OldbookInfo# " .. filetype .. "  " .. (vim.bo.fileencoding ~= "" and vim.bo.fileencoding or "utf-8")
            .. "  " .. vim.bo.fileformat .. " ",
        "%#OldbookPositionEdge#",
        "%#OldbookPosition# 󰉸 %l:%c  %P ",
    })
    return left .. "%=" .. right
end

function _G.oldbook_winbar()
    if vim.bo.buftype ~= "" then return "" end
    local name = vim.fn.expand("%:~:.")
    if name == "" then name = "[No Name]" end
    local modified = vim.bo.modified and "  %#OldbookWinbarModified#●" or ""
    return "%#OldbookWinbarIcon# 󰈔 %#WinBar#" .. name .. modified
end

vim.opt.statusline = "%!v:lua.oldbook_statusline()"
vim.opt.winbar = "%{%v:lua.oldbook_winbar()%}"
vim.api.nvim_create_autocmd({ "BufEnter", "DirChanged", "FocusGained" }, {
    callback = function() checkout_branch() end,
})
