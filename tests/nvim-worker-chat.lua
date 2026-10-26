-- Integration contract for the native chat presentation, without an API request.
vim.g.spaceghost_no_shell = true
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
dofile(vim.fn.getcwd() .. '/.config/nvim/init.lua')
assert(require('spaceghost.agent').load(), 'Agentic not installed')
local config = require('agentic.config')
assert(type(config.headers.chat) == 'function', 'worker chat header not configured')
local state = {
  get_model_name = function() return 'Test model' end,
  get_mode_name = function() return 'Workspace access' end,
  get_context_used_raw = function() return 25 end,
  get_context_size_raw = function() return 100 end,
}
local text = config.headers.chat({ title = 'chat' }, state)
assert(text:find('CODEX', 1, true), 'Codex brand missing')
assert(text:find('Test model', 1, true), 'model missing')
assert(text:find('25%', 1, true), 'measured context usage missing')
state.get_model_name = function() return '%{g:worker_header_injected}' end
vim.g.worker_header_injected = 'EVALUATED'
local escaped = config.headers.chat({ title = 'chat' }, state)
local rendered = vim.api.nvim_eval_statusline(escaped, { use_winbar = true }).str
assert(rendered:find('%{g:worker_header_injected}', 1, true), 'model text became executable winbar syntax')
assert(not rendered:find('EVALUATED', 1, true), 'winbar evaluated untrusted text')
vim.t.spaceghost_name = '%{g:worker_header_injected}'
local tabline = vim.api.nvim_eval_statusline(Spaceghost.ui.tabline(), { use_tabline = true, maxwidth = 200 }).str
assert(not tabline:find('EVALUATED', 1, true), 'worker tab label evaluated format syntax')
vim.t.spaceghost_name = nil
local Animation = require('agentic.ui.status_animation')
local buf = vim.api.nvim_create_buf(false, true)
local animation = Animation:new(buf)
animation:start('thinking')
assert(not animation._next_frame_handle, 'hidden worker retained animation timer')
vim.api.nvim_set_current_buf(buf)
vim.g.spaceghost_worker_motion = false
animation:start('thinking')
assert(animation._extmark_id and not animation._next_frame_handle, 'disabled motion kept animation timer')
animation:stop()
vim.g.spaceghost_worker_motion = true
local original = config.headers.chat
local old_hud_timer = _G.spaceghost_hud_timer
require('spaceghost.deck').reload()
require('spaceghost.agent').load()
assert(type(config.headers.chat) == 'function', 'header lost on reload')
assert(config.headers.chat ~= original, 'header retained stale module')
assert(_G.spaceghost_hud_timer ~= old_hud_timer and old_hud_timer:is_closing(), 'HUD timer stacked on reload')
print('PASS rich escaped chat headers, hidden/reduced-motion animation and config reload')
vim.cmd('qa!')
