-- Loads libspaceghost.so (Nelua, built by ~/.bin/spaceghost-native) through LuaJIT
-- FFI. Every entry point has a pure Lua fallback so the config works untouched on a
-- host without the toolchain; `M.backend` tells the HUD which one is active.
local M = { backend = 'lua' }

local lib_path = (vim.env.XDG_DATA_HOME or (vim.env.HOME .. '/.local/share'))
  .. '/nvim/spaceghost/libspaceghost.so'
M.lib_path = lib_path

local ffi_ok, ffi = pcall(require, 'ffi')
local lib
if ffi_ok and (vim.uv or vim.loop).fs_stat(lib_path) then
  local ok, err = pcall(function()
    ffi.cdef [[
      typedef struct {
        double load1, load5, load15;
        int64_t mem_total_kb, mem_avail_kb;
        int32_t battery_pct;
        bool battery_charging;
        int64_t uptime_s;
      } spaceghost_telemetry_t;
      bool spaceghost_telemetry(spaceghost_telemetry_t* t);
      size_t spaceghost_osc7_path(const char* seq, char* out, size_t cap);
      size_t spaceghost_short_path(const char* path, const char* home, char* out, size_t cap);
      int32_t spaceghost_abi(void);
    ]]
    lib = ffi.load(lib_path)
    if lib.spaceghost_abi() ~= 1 then error('libspaceghost ABI mismatch; run spaceghost-native') end
  end)
  if ok then M.backend = 'nelua' else lib = nil; M.error = tostring(err) end
end

local function read(path)
  local f = io.open(path, 'r')
  if not f then return nil end
  local s = f:read('*a'); f:close()
  return s
end

-- { load1, load5, load15, mem_total_kb, mem_avail_kb, battery_pct, battery_charging, uptime_s }
function M.telemetry()
  if lib then
    local t = ffi.new('spaceghost_telemetry_t')
    if not lib.spaceghost_telemetry(t) then return nil end
    return {
      load1 = t.load1, load5 = t.load5, load15 = t.load15,
      mem_total_kb = tonumber(t.mem_total_kb), mem_avail_kb = tonumber(t.mem_avail_kb),
      battery_pct = t.battery_pct, battery_charging = t.battery_charging,
      uptime_s = tonumber(t.uptime_s),
    }
  end
  local la = read('/proc/loadavg')
  if not la then return nil end
  local l1, l5, l15 = la:match('^(%S+)%s+(%S+)%s+(%S+)')
  local mem = read('/proc/meminfo') or ''
  local t = {
    load1 = tonumber(l1) or -1, load5 = tonumber(l5) or -1, load15 = tonumber(l15) or -1,
    mem_total_kb = tonumber(mem:match('MemTotal:%s*(%d+)')) or -1,
    mem_avail_kb = tonumber(mem:match('MemAvailable:%s*(%d+)')) or -1,
    battery_pct = -1, battery_charging = false,
    uptime_s = tonumber((read('/proc/uptime') or ''):match('^(%d+)')) or -1,
  }
  for _, name in ipairs({ 'BAT0', 'BAT1', 'macsmc-battery', 'battery' }) do
    local cap = read('/sys/class/power_supply/' .. name .. '/capacity')
    if cap then
      t.battery_pct = tonumber(cap:match('%d+')) or -1
      t.battery_charging = ((read('/sys/class/power_supply/' .. name .. '/status') or ''):match('^%S+') == 'Charging')
      break
    end
  end
  return t
end

-- OSC 7 sequence -> decoded path, or nil.
function M.osc7_path(seq)
  if lib then
    local buf = ffi.new('char[?]', 4096)
    local n = tonumber(lib.spaceghost_osc7_path(seq, buf, 4096))
    if n == 0 then return nil end
    return ffi.string(buf, n)
  end
  local rest = seq:match('^\27%]7;file://([^\7\27]*)')
  if not rest then return nil end
  local path = rest:match('(/.*)$')
  if not path then return nil end
  return (path:gsub('%%(%x%x)', function(h) return string.char(tonumber(h, 16)) end))
end

-- /home/jack/.files/.config/nvim -> ~/.f/.c/nvim
function M.short_path(path)
  local home = vim.env.HOME or ''
  if lib then
    local buf = ffi.new('char[?]', 4096)
    local n = tonumber(lib.spaceghost_short_path(path, home, buf, 4096))
    return ffi.string(buf, n)
  end
  if home ~= '' and path:sub(1, #home) == home then path = '~' .. path:sub(#home + 1) end
  local parts = {}
  for piece in path:gmatch('[^/]+') do parts[#parts + 1] = piece end
  local out = path:sub(1, 1) == '/' and '/' or ''
  for i, piece in ipairs(parts) do
    if i < #parts then
      out = out .. piece:sub(1, piece:sub(1, 1) == '.' and 2 or 1) .. '/'
    else
      out = out .. piece
    end
  end
  return out
end

return M
