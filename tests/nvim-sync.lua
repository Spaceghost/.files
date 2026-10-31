-- Run: nvim --headless -u NONE -i NONE -l tests/nvim-sync.lua
vim.opt.runtimepath:prepend(vim.fn.getcwd() .. '/.config/nvim')
package.loaded['spaceghost.shell'] = { is_server = true }
local calls, exit = 0, nil
local original = vim.fn.jobstart
vim.fn.jobstart = function(argv, opts)
  assert(argv[1]:match('/.bin/spaceghost%-sync$') and argv[2] == 'run')
  assert(opts.detach, 'sync must survive editor shutdown')
  calls = calls + 1
  exit = opts.on_exit
  return 123
end
local sync = require('spaceghost.sync')
sync.setup()
local state = _G.spaceghost_sync_state
local first = state.timer
assert(first and not first:is_closing(), 'server needs a backup schedule')
assert(vim.wait(4500, function() return calls == 1 end, 10), 'backup schedule did not run')
sync.run()
assert(calls == 1, 'launched a duplicate sync job')
package.loaded['spaceghost.sync'] = nil
sync = require('spaceghost.sync')
sync.setup()
assert(first:is_closing() and state.timer ~= first, 'reload stacked timers')
assert(state.job == 123, 'reload lost the active sync')
exit(123, 0)
assert(state.job == nil and state.last_exit == 0, 'exit status not retained')
sync.run()
assert(calls == 2, 'next sync was blocked after completion')
exit(123, 1)
assert(state.last_exit == 1, 'failure status not retained')
package.loaded['spaceghost.shell'].is_server = false
local last = state.timer
sync.setup()
assert(last:is_closing() and state.timer == nil, 'standalone editor retained a scheduler')
vim.fn.jobstart = original
print('PASS automatic sync scheduling, reload, in-flight jobs and standalone isolation')
vim.cmd('qa!')
