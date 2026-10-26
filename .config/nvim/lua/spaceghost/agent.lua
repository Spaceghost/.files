-- Native Codex application. Dependencies are installed explicitly, never on startup.
local M = {}
local origin_cwd

function M.cwd()
  local buf = vim.api.nvim_get_current_buf()
  if vim.bo[buf].buftype == '' then
    local name = vim.api.nvim_buf_get_name(buf)
    if name ~= '' then return vim.fs.dirname(name) end
  end
  return require('spaceghost.shell').cwd(buf)
end

function M.load()
  if package.loaded['agentic'] then
    -- F4 r reloads this module while Agentic and its running sessions survive.
    require('agentic.config').acp_configs.session_cwd = function() return origin_cwd or M.cwd() end
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
  return require('agentic')
end

function M.run(action)
  -- Session initialization is asynchronous and can run after focus leaves the file/shell.
  origin_cwd = M.cwd()
  local agent = M.load()
  if not agent then return end
  if action == 'toggle' then agent.toggle({ auto_add_to_context = false })
  elseif action == 'new_session' then
    local cwd = origin_cwd
    agent.new_session({ auto_add_to_context = false, cwd = function() return cwd end })
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
      elseif name == 'new_session' then agent.new_session({ auto_add_to_context = false, cwd = function() return cwd end })
      else agent[name]() end
    end
  end
  require('spaceghost.deck').menu('Codex / Agentic', {
    { key = 'i', label = 'Toggle native Codex chat', action = action('toggle') },
    { key = 'n', label = 'New session here', action = action('new_session') },
    { key = 's', label = 'Choose live session', action = action('select_session') },
    { key = 'r', label = 'Restore saved Codex session', action = action('restore_session') },
    { key = 'l', label = 'Rotate chat layout', action = action('rotate_layout') },
  })
end

function M.setup()
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
end

return M
