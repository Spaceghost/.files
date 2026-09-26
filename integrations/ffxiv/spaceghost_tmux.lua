-- User module for GhosttyDalamud's lua/ directory. No credentials live here.
local M = {}

function M.apply(config, command, view)
  assert(type(config) == 'table' and type(config.profiles) == 'table', 'Ghostty profiles missing')
  assert(type(command) == 'table' and #command > 0, 'tmux SSH command missing')
  for _, argument in ipairs(command) do
    assert(type(argument) == 'string' and argument ~= '', 'invalid command argument')
  end
  local name = 'Spaceghost / bak / ' .. view
  local index
  for i, profile in ipairs(config.profiles) do
    if profile.name == name then index = i; break end
  end
  local profile = { name = name, transport = 'agent', command = command }
  if index then
    config.profiles[index] = profile
  else
    table.insert(config.profiles, profile)
    index = #config.profiles
  end
  config.default_profile = index
  return config
end

return M
