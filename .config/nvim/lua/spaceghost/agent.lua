-- Native Codex application. Dependencies are installed explicitly, never on startup.
local M = {}
local origin_cwd

local function plain(text)
  -- Winbars parse % expressions: never treat names or model text as format code.
  return tostring(text or ''):gsub('[%c]', ' '):gsub('%%', '%%%%')
end

function M.chat_header(_, session_state)
  local name, status, elapsed = 'SPACEGHOST', nil, nil
  local registry = package.loaded['agentic.session_registry']
  local workers = package.loaded['spaceghost.workers']
  if registry and workers then
    for _, worker in ipairs(workers.list()) do
      local session = worker.session_key and registry.get(worker.session_key)
      if session and session.session_state == session_state then
        name, status = worker.name, worker.status
        if worker.started_at then
          local seconds = math.max(0, (worker.finished_at or os.time()) - worker.started_at)
          elapsed = string.format('%02d:%02d', math.floor(seconds / 60), seconds % 60)
        end
        break
      end
    end
  end
  local pieces = { 'CODEX / ' .. plain(name) }
  if status then pieces[#pieces + 1] = plain(status:upper()) end
  if elapsed then pieces[#pieces + 1] = elapsed end
  if session_state then
    local model = session_state:get_model_name()
    if model then pieces[#pieces + 1] = plain(model) end
    local mode = session_state:get_mode_name()
    if mode then pieces[#pieces + 1] = plain(mode) end
    local used, size = session_state:get_context_used_raw(), session_state:get_context_size_raw()
    if used and size and size > 0 then
      pieces[#pieces + 1] = string.format('CTX %d%%%%', math.floor(used / size * 100 + 0.5))
    end
  end
  return table.concat(pieces, '  ·  ')
end

function M.animate_frame(animation, epoch)
  if epoch ~= animation._epoch or not animation._state then return end
  animation._next_frame_handle = nil
  local visible = false
  for _, win in ipairs(vim.fn.win_findbuf(animation._bufnr)) do
    if vim.api.nvim_win_is_valid(win)
      and not vim.api.nvim_win_get_config(win).hide
      and vim.api.nvim_win_get_tabpage(win) == vim.api.nvim_get_current_tabpage() then
      visible = true
      break
    end
  end
  if not visible then return end
  local motion = vim.g.spaceghost_worker_motion ~= false
  if not motion and animation._spaceghost_static_epoch == epoch then return end
  local class = require('agentic.ui.status_animation')
  class._spaceghost_render_frame(animation, epoch)
  if not motion then
    if animation._next_frame_handle then
      animation._next_frame_handle:stop()
      if not animation._next_frame_handle:is_closing() then animation._next_frame_handle:close() end
      animation._next_frame_handle = nil
    end
    animation._spaceghost_static_epoch = epoch
  end
end

function M.configure()
  local config = require('agentic.config')
  config.headers.chat = M.chat_header
  config.headers.input = { title = 'PROMPT', suffix = 'Ctrl-s send · Shift-Tab mode · Ctrl-\\ o workers' }
  config.headers.todos = { title = 'PLAN / LIVE PROGRESS' }
  local frames = { '⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏' }
  config.spinner_chars.generating = frames
  config.spinner_chars.thinking = frames
  config.spinner_chars.searching = { '◐', '◓', '◑', '◒' }
  local animation = require('agentic.ui.status_animation')
  if not animation._spaceghost_render_frame then
    animation._spaceghost_render_frame = animation._render_frame
    animation._render_frame = function(self, epoch)
      return require('spaceghost.agent').animate_frame(self, epoch)
    end
  end
  require('spaceghost.workers').attach()
end

function M.cwd()
  local buf = vim.api.nvim_get_current_buf()
  if vim.bo[buf].buftype == '' then
    local name = vim.api.nvim_buf_get_name(buf)
    if name ~= '' then return vim.fs.dirname(name) end
  end
  local workers = package.loaded['spaceghost.workers']
  if workers and vim.bo[buf].buftype ~= 'terminal' then
    for _, worker in ipairs(workers.list()) do
      if worker.tab == vim.api.nvim_get_current_tabpage() and worker.cwd then return worker.cwd end
    end
  end
  return require('spaceghost.shell').cwd(buf)
end

function M.load()
  if package.loaded['agentic'] then
    -- F4 r reloads this module while Agentic and its running sessions survive.
    require('agentic.config').acp_configs.session_cwd = function() return origin_cwd or M.cwd() end
    M.configure()
    return require('agentic')
  end
  local adapter = vim.fn.stdpath('data') .. '/spaceghost/agentic/node_modules/.bin/codex-acp'
  local ok = pcall(vim.cmd.packadd, 'agentic.nvim')
  if not ok or vim.fn.executable(adapter) ~= 1 then
    vim.notify('Install Codex UI: ~/.bin/spaceghost-agentic-install', vim.log.levels.WARN)
    return
  end
  local tmpdir = vim.fn.stdpath('cache') .. '/agentic-tmp'
  vim.fn.mkdir(tmpdir, 'p')
  require('agentic').setup({
    provider = 'codex-acp',
    acp_providers = {
      ['codex-acp'] = {
        name = 'Codex', command = adapter, args = {},
        default_mode = 'workspace-write',
        env = { TMPDIR = tmpdir },
      },
    },
    acp_configs = { session_cwd = function() return origin_cwd or M.cwd() end },
    windows = { position = 'right', width = '42%', input = { height = 7 } },
    diff_preview = { enabled = true, layout = 'split' },
  })
  M.configure()
  return require('agentic')
end

function M.run(action)
  -- Session initialization is asynchronous and can run after focus leaves the file/shell.
  origin_cwd = M.cwd()
  local agent = M.load()
  if not agent then return end
  if action == 'toggle' then agent.toggle({ auto_add_to_context = false })
  elseif action == 'new_session' then
    return require('spaceghost.workers').new({ cwd = origin_cwd })
  else agent[action]() end
end

function M.menu()
  -- Capture before the floating menu takes focus.
  local cwd = M.cwd()
  local function action(name)
    return function()
      origin_cwd = cwd
      local agent = M.load()
      if not agent then return end
      if name == 'toggle' then agent.toggle({ auto_add_to_context = false })
      elseif name == 'new_session' then require('spaceghost.workers').new({ cwd = cwd })
      else agent[name]() end
    end
  end
  require('spaceghost.deck').menu('Codex / Agentic', {
    { key = 'o', label = 'Worker dashboard / activity + inbox', action = function() require('spaceghost.worker_ui').open() end },
    { key = 'i', label = 'Toggle native Codex chat', action = action('toggle') },
    { key = 'n', label = 'New session here', action = action('new_session') },
    { key = 's', label = 'Choose live session', action = action('select_session') },
    { key = 'r', label = 'Restore saved Codex session', action = action('restore_session') },
    { key = 'l', label = 'Rotate chat layout', action = action('rotate_layout') },
  })
end

function M.setup()
  require('spaceghost.workers').setup()
  local group = vim.api.nvim_create_augroup('SpaceghostAgent', { clear = true })
  vim.api.nvim_create_autocmd({ 'BufEnter', 'FileType' }, {
    group = group,
    callback = function(ev)
      if vim.bo[ev.buf].filetype ~= 'AgenticInput' then return end
      vim.schedule(function()
        if vim.api.nvim_get_current_buf() == ev.buf then vim.cmd.startinsert() end
      end)
    end,
  })
  local commands = {
    Codex = 'toggle', CodexNew = 'new_session', CodexSessions = 'select_session',
    CodexRestore = 'restore_session', CodexAdd = 'add_selection_or_file_to_context',
    CodexDiagnostics = 'add_buffer_diagnostics', CodexLayout = 'rotate_layout',
  }
  for command, action in pairs(commands) do
    vim.api.nvim_create_user_command(command, function() M.run(action) end, { force = true })
  end
  vim.api.nvim_create_user_command('CodexMenu', M.menu, { force = true })
  -- A live reload adopts already-running Agentic sessions without restarting them.
  if package.loaded['agentic'] then M.configure() end
end

return M
