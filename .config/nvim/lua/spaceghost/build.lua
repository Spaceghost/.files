-- One tracked build at a time, shown in the shared status line across tabs.
local M = {}
local state = rawget(_G, 'spaceghost_build_state') or { status = 'idle', lines = {} }
_G.spaceghost_build_state = state

local function refresh()
  if #vim.api.nvim_list_uis() > 0 then vim.schedule(function() pcall(vim.cmd.redrawstatus) end) end
end

local function append(lines)
  for _, line in ipairs(lines or {}) do
    if line ~= '' then state.lines[#state.lines + 1] = line end
  end
  while #state.lines > 500 do table.remove(state.lines, 1) end
  refresh()
end

function M.start(command)
  if command == '' then vim.notify('Usage: :Build {command}', vim.log.levels.WARN); return end
  if state.status == 'running' then vim.notify('A build is already running', vim.log.levels.WARN); return end
  state.command, state.lines, state.status = command, {}, 'running'
  state.started_at, state.finished_at, state.code = os.time(), nil, nil
  local cwd = require('spaceghost.shell').cwd(0)
  local script = 'source "$HOME/.local/bin/agent-storage-env" spaceghost-build && eval "$1"'
  local job = vim.fn.jobstart({ 'bash', '-lc', script, 'spaceghost-build', command }, {
    cwd = cwd, stdout_buffered = false, stderr_buffered = false,
    on_stdout = function(_, lines) append(lines) end,
    on_stderr = function(_, lines) append(lines) end,
    on_exit = function(_, code)
      state.code, state.finished_at = code, os.time()
      state.status, state.job = code == 0 and 'passed' or 'failed', nil
      refresh()
      vim.notify('Build ' .. state.status .. ' (' .. code .. ')')
    end,
  })
  if job <= 0 then
    state.status = 'failed'
    state.code = job
    vim.notify('Could not start build', vim.log.levels.ERROR)
  else
    state.job = job
  end
  refresh()
end

function M.stop()
  if state.status == 'running' and state.job then vim.fn.jobstop(state.job) end
end

function M.prompt()
  vim.ui.input({ prompt = 'Build command: ', default = state.command or '' }, function(command)
    if command and command ~= '' then M.start(command) end
  end)
end

function M.log()
  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].bufhidden = 'wipe'
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, #state.lines > 0 and state.lines or { 'No build output yet' })
  local width = math.max(20, math.floor(vim.o.columns * .8))
  local height = math.max(5, math.floor((vim.o.lines - 2) * .7))
  vim.api.nvim_open_win(buf, true, {
    relative = 'editor', width = width, height = height,
    row = math.max(0, math.floor((vim.o.lines - height) / 2)),
    col = math.max(0, math.floor((vim.o.columns - width) / 2)),
    style = 'minimal', border = 'rounded', title = ' BUILD LOG ',
  })
  vim.keymap.set('n', 'q', '<Cmd>close<CR>', { buffer = buf, silent = true })
end

function M.statusline()
  local labels = { idle = 'idle', running = 'running', passed = 'passed', failed = 'failed' }
  local group = state.status == 'failed' and 'SpaceghostStatusAlert'
    or state.status == 'running' and 'SpaceghostStatusWarn' or 'SpaceghostStatusCwd'
  local label = labels[state.status] or state.status
  local detail = state.status == 'running' and state.command or nil
  if detail then detail = ' ' .. vim.fn.strcharpart(detail, 0, 18):gsub('%%', '%%%%') end
  return '%#' .. group .. '#BUILD ' .. label .. (detail or '') .. '%#StatusLine# '
end

function M.setup()
  vim.api.nvim_create_user_command('Build', function(opts) M.start(opts.args) end, { nargs = '+', complete = 'shellcmd', force = true })
  vim.api.nvim_create_user_command('BuildLog', M.log, { force = true })
  vim.api.nvim_create_user_command('BuildStop', M.stop, { force = true })
end

return M
