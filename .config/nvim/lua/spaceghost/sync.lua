-- A backup schedule owned by the persistent editor, independent of systemd.
-- The sync worker's flock serializes this with the host timer/cron schedule.
local M = {}
local uv = vim.uv or vim.loop
local state = rawget(_G, 'spaceghost_sync_state') or {}
_G.spaceghost_sync_state = state

function M.run()
  if state.job then return end
  local script = vim.fn.expand('~/.bin/spaceghost-sync')
  if vim.fn.executable(script) ~= 1 then return end
  state.last_run = os.time()
  local job = vim.fn.jobstart({ script, 'run' }, {
    detach = true,
    on_exit = function(_, code)
      state.job, state.last_exit = nil, code
    end,
  })
  if job > 0 then state.job = job else state.last_exit = job end
end

function M.setup()
  if state.timer and not state.timer:is_closing() then
    state.timer:stop()
    state.timer:close()
  end
  state.timer = nil
  if not require('spaceghost.shell').is_server then return end
  local timer = uv.new_timer()
  state.timer = timer
  timer:start(3000, 120000, vim.schedule_wrap(M.run))
  timer:unref()
  local group = vim.api.nvim_create_augroup('SpaceghostSync', { clear = true })
  vim.api.nvim_create_autocmd('VimLeavePre', { group = group, callback = function()
    if not timer:is_closing() then timer:stop(); timer:close() end
  end })
end

return M
