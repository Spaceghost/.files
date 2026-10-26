-- Agentic remains the owner of sessions and permissions. This store survives config reloads.
local M = {}
local S = rawget(_G, 'spaceghost_workers_state')
if not S then
  S = { records = {}, order = {}, next_id = 0, next_message = 0, subscribers = {}, wrappers = {} }
  rawset(_G, 'spaceghost_workers_state', S)
end
S.api = M
local LIMIT = { queue = 32, inbox = 100, events = 100, text = 16384, hops = 8, tools = 128, children = 64 }
local function clean(s, max) return tostring(s or ''):gsub('[%z\1-\8\11\12\14-\31\127]', ''):sub(1, max or 512) end
local function notify(quiet)
  for _, cb in pairs(S.subscribers) do pcall(cb, quiet and 'tick' or 'change') end
  -- Lifecycle hooks can run inside a tab/layout mutation. Redraw only after it
  -- completes, and never ask a detached/headless instance to allocate a grid.
  if not quiet and not S.redraw_pending and #vim.api.nvim_list_uis()>0 then
    S.redraw_pending=true
    vim.schedule(function()
      S.redraw_pending=nil
      if #vim.api.nvim_list_uis()>0 then pcall(vim.cmd,'redrawstatus') end
    end)
  end
end
local function event(r, text, kind)
  r.last_at = os.time()
  r.events[#r.events + 1] = { at = r.last_at, text = clean(text), kind = kind or 'activity' }
  if #r.events > LIMIT.events then table.remove(r.events, 1) end
  local widget = r._session and r._session.widget
  if widget and widget.schedule_header_refresh then widget:schedule_header_refresh() end
  notify()
end
local function changed_file(r, path)
  path=clean(path,1024)
  if r.changed_files[path] then return end
  local count=0; for _ in pairs(r.changed_files) do count=count+1 end
  if count<512 then r.changed_files[path]=true end
end
local function record(cwd, name)
  S.next_id = S.next_id + 1
  local id = ('w%03d'):format(S.next_id)
  local r = { id = id, name = clean(name or ('Worker ' .. S.next_id), 120), cwd = cwd,
    status = 'starting', activity = 'Starting session', started_at = os.time(), last_at = os.time(),
    plan = {}, usage = {}, changed_files = {}, tools = {}, children = {}, inbox = {}, queue = {},
    unread = 0, bridge = false, events = {}, _workspace_captured = cwd ~= nil }
  S.records[id] = r; S.order[#S.order + 1] = id
  return r
end
local function session(r)
  local reg = package.loaded['agentic.session_registry']
  local s = r and reg and reg.get(r.session_key)
  if s and not s._destroyed and s == r._session then return s end
end
local function adopt(s, r)
  r = r or S.records[s._spaceghost_worker_id]
  if not r then
    -- Agentic does not retain the origin of sessions created before tracking.
    r = record(nil, s.chat_history and s.chat_history.title or s.title)
  end
  if r._workspace_captured==nil then
    -- Upgrade the live store: only bridge-enabled starts prove the old tracker
    -- captured a workspace at its request seam. Migrated sessions did not.
    r._workspace_captured=r.bridge==true
    if not r._workspace_captured then r.cwd=nil end
  end
  s._spaceghost_worker_id = r.id; r._session = s; r.session_key = s.session_key
  -- The request callback can precede Agentic's scheduled complete_start callback.
  r.session_id = s.session_id or r.session_id
  if s.widget and s.widget.get_visible_tab_id then r.tab = s.widget:get_visible_tab_id() or r.tab end
  return r
end
local function lookup(data)
  for _, r in pairs(S.records) do
    if (data.session_key and r.session_key == data.session_key) or (data.session_id and r.session_id == data.session_id) then return r end
  end
end
local function wrap(tbl, key, factory)
  local current = tbl[key]
  if type(current) ~= 'function' then error('Unsupported Agentic version: missing ' .. key) end
  local installed=S.wrappers[current]
  if type(installed)=='table' and installed.version==2 then return end
  if type(installed)=='table' then
    current=installed.original
  elseif installed then
    -- The first release retained only a boolean. Recover its named original
    -- upvalue once so upgrading an active editor replaces, rather than nests,
    -- request/callback wrappers. All first-release factories used this name.
    local original
    for i=1,100 do
      local name,value=debug.getupvalue(current,i)
      if not name then break end
      if name=='original' and type(value)=='function' then original=value; break end
    end
    assert(original,'Cannot upgrade legacy worker wrapper: '..key)
    current=original
  end
  local wrapped = factory(current)
  S.wrappers[wrapped] = {version=2,original=current}; tbl[key] = wrapped
end
function M.state() return S end
function M.get(id) return S.records[id] end
function M.list()
  local out = {}; for _, id in ipairs(S.order) do if S.records[id] then out[#out+1] = S.records[id] end end
  return out
end
function M.subscribe(key, callback) S.subscribers[key] = callback end
function M.summary()
  local n = { total = 0, running = 0, waiting = 0, done = 0, failed = 0, unread = 0 }
  for _, r in ipairs(M.list()) do
    n.total = n.total + 1; n.unread = n.unread + r.unread
    if n[r.status] ~= nil then n[r.status] = n[r.status] + 1
    elseif r.status ~= 'ready' then n.running = n.running + 1 end
  end
  return n
end
local function pending(r)
  local s = session(r)
  return s and s.permission_manager and s.permission_manager:has_pending()
end
local function clear_queue(r, status)
  for _,msg in ipairs(r.queue) do msg.status=status end
  r.queue={}
end
local function arm()
  if S.timer then return end
  S.timer = vim.uv.new_timer()
  S.timer:start(250, 250, vim.schedule_wrap(function() S.api.tick() end))
end
function M.tick()
  local active, changed = false, false
  for _, r in ipairs(M.list()) do
    local s = session(r)
    if s then
      r.session_id = s.session_id or r.session_id
      if s.session_state and s.session_state.get_model_name then
        local ok,model=pcall(s.session_state.get_model_name,s.session_state)
        if ok and model then r.model=clean(model,120) end
      end
      if r.tab and not vim.api.nvim_tabpage_is_valid(r.tab) then r.tab = nil; changed = true end
      if s._connection_error or s._session_creation_failed then
        if r.status ~= 'failed' then r.status = 'failed'; r.error = 'Session unavailable'; changed = true end
        r._fatal=true
        clear_queue(r,'failed')
      elseif r._stopping then
        -- Only the outstanding session/prompt response acknowledges cancel.
        -- Permission callbacks and tool updates cannot release this gate.
        if r.status~='stopping' then r.status='stopping'; changed=true end
      elseif pending(r) then
        if r.status ~= 'waiting' then r.status = 'waiting'; r.activity = 'Approval requested'; changed = true end
      elseif s.is_generating then
        if r.status == 'ready' or r.status == 'starting' or r.status == 'waiting' or r.status == 'done' then r.status = 'thinking'; changed = true end
      elseif s.session_id then
        if r.status == 'starting' or r.status == 'waiting' then r.status = 'ready'; changed = true end
        if #r.queue > 0 and not r._dispatching and not r._fatal and r.status ~= 'stopping' then
          -- No scheduled boundary between checking identity/permissions and submitting.
          local msg = table.remove(r.queue, 1)
          r._dispatching = msg
          local ok, err = pcall(s._handle_input_submit, s, msg.prompt)
          r._dispatching = false
          if ok and s.is_generating then
            msg.status = 'delivered'; msg.delivered_at = os.time(); r.status = 'thinking'
            r._active_peer = msg.from and msg or nil
            r.started_at = os.time(); r.finished_at = nil; event(r, 'Prompt delivered', 'prompt')
          else
            msg.status = 'failed'; r.error = clean(err or 'Agentic did not accept prompt'); event(r, r.error, 'error')
          end
          changed = true
        end
      end
      if r.status~='failed' and (#r.queue > 0 or not s.session_id or s.is_generating) then active = true end
      local visible=s.widget and s.widget.get_visible_tab_id and s.widget:get_visible_tab_id()
      if visible and visible==vim.api.nvim_get_current_tabpage() then
        if r._header_at~=os.time() then
          r._header_at=os.time()
          if s.widget.schedule_header_refresh then pcall(s.widget.schedule_header_refresh,s.widget) end
        end
        local animation=s.status_animation
        if vim.g.spaceghost_worker_motion~=false and animation and animation._state and not animation._next_frame_handle and animation._render_frame then
          pcall(animation._render_frame,animation,animation._epoch)
        end
      end
    elseif r._session and r.status ~= 'failed' then
      r.status = 'failed'; r._fatal=true; r.error = 'Session destroyed'; clear_queue(r,'failed'); changed = true
      local ok, bus = pcall(require, 'spaceghost.worker_bus'); if ok then bus.revoke(r.id) end
    end
  end
  if active then arm()
  elseif S.timer then S.timer:stop(); S.timer:close(); S.timer = nil end
  if changed then notify() elseif active then notify(true) end
end
local function enqueue(r, text, opts)
  if type(text) ~= 'string' or text:match('^%s*$') then return nil, 'Message must contain text' end
  if #text > LIMIT.text then return nil, 'Message exceeds 16384 bytes' end
  if not r or not session(r) then return nil, 'Unknown or destroyed worker' end
  local s=session(r)
  if r._fatal or s._connection_error or s._session_creation_failed then return nil, 'Worker is unavailable' end
  if r.status=='failed' and s.session_id then r.status='ready'; r.error=nil end
  if #r.queue >= LIMIT.queue then return nil, 'Worker queue is full' end
  S.next_message = S.next_message + 1
  local m = { id = 'm' .. S.next_message, to = r.id, text = text, at = os.time(), status = 'queued',
    from = opts.from, reply_to = opts.reply_to, hops = opts.hops or 0 }
  m.prompt = text
  if m.from then
    local sender = S.records[m.from]
    m.prompt = ('[Worker message %s from %s (%s); hop %d; reply_to %s]\n%s'):format(m.id, m.from, clean(sender.name,120), m.hops, m.reply_to or 'none', text)
    r.inbox[#r.inbox+1] = m
    if #r.inbox > LIMIT.inbox then
      local evicted=table.remove(r.inbox,1)
      if not evicted.read_at then r.unread=math.max(0,r.unread-1) end
    end
    r.unread = r.unread + 1
  end
  r.queue[#r.queue+1] = m; event(r, 'Message queued' .. (m.from and (' from ' .. m.from) or ''), 'message')
  arm(); return m
end
function M.send(id, text, opts) return enqueue(S.records[id], text, opts or {}) end
function M.read(id, message_ids)
  local r=S.records[id]
  if not r then return nil,'Unknown worker' end
  local wanted={}
  for _,message_id in ipairs(message_ids or {}) do wanted[message_id]=true end
  local count=0
  for _,message in ipairs(r.inbox) do
    if wanted[message.id] and not message.read_at then
      message.read_at=os.time(); count=count+1
    end
  end
  if count>0 then r.unread=math.max(0,r.unread-count); notify() end
  return count
end
function M.peer(from, to, text, opts)
  opts = opts or {}
  if not S.records[from] or not session(S.records[from]) then return nil, 'Unknown sender' end
  if from == to then return nil, 'Cannot message self' end
  local hops = 1
  local reply_to=opts.reply_to or (S.records[from]._active_peer and S.records[from]._active_peer.id)
  if reply_to then
    local parent
    for _, m in ipairs(S.records[from].inbox) do if m.id == reply_to then parent = m; break end end
    if not parent then return nil, 'Unknown reply message' end
    hops = parent.hops + 1
  end
  if hops > LIMIT.hops then return nil, 'Conversation hop limit reached' end
  return enqueue(S.records[to], text, { from = from, reply_to = reply_to, hops = hops })
end
function M.rename(id, name)
  local r = S.records[id]; if not r then return nil, 'Unknown worker' end
  r.name = clean(name,120)
  if r.tab and vim.api.nvim_tabpage_is_valid(r.tab) then vim.t[r.tab].spaceghost_name=r.name end
  notify(); return r
end
function M.open(id)
  local r = S.records[id]; local s = session(r)
  if not s then return nil, 'Worker session is unavailable' end
  -- A widget already visible in a different tab must be focused there.
  local tab = s.widget:get_visible_tab_id() or r.tab
  if not tab or not vim.api.nvim_tabpage_is_valid(tab) then vim.cmd('tabnew'); tab = vim.api.nvim_get_current_tabpage() end
  vim.api.nvim_set_current_tabpage(tab); r.tab = tab
  vim.t[tab].spaceghost_name=r.name
  require('agentic.session_registry').show_session(r.session_key, { auto_add_to_context = false })
  notify(); return r
end
function M.stop(id)
  local r = S.records[id]; local s = session(r); if not s then return nil, 'Worker session is unavailable' end
  clear_queue(r,'cancelled')
  if r._stopping then return r end
  if s.is_generating and s.session_id then
    r._stopping=true; r.status='stopping'; r.activity='Stopping turn'
    s.agent:stop_generation(s.session_id)
    -- Reject pending permissions, but retain generation ownership until the
    -- original response arrives. Cancel is only a notification in ACP.
    s.permission_manager:clear()
    event(r,'Cancellation requested','stop'); arm()
  else
    s.permission_manager:clear()
    if s.status_animation then s.status_animation:stop() end
    r.status='done'; r.finished_at=os.time(); event(r,'Turn stopped','stop')
  end
  return r
end
function M.dismiss(id)
  local r = S.records[id]; if not r then return nil, 'Unknown worker' end
  local s = session(r)
  if s and (r._stopping or s.is_generating or pending(r) or #r.queue > 0) then return nil, 'Stop the worker before dismissing it' end
  r._dismissed = true; S.records[id] = nil
  local ok,bus = pcall(require,'spaceghost.worker_bus'); if ok then bus.revoke(id) end
  notify(); return true
end
function M.new(opts)
  opts = opts or {}
  local cwd = vim.fs.normalize(opts.cwd or require('spaceghost.agent').cwd())
  if not package.loaded['agentic'] then
    if not require('spaceghost.agent').load() then return nil, 'Agentic is unavailable' end
  end
  M.attach()
  local origin = vim.api.nvim_get_current_tabpage()
  vim.cmd('tabnew'); local tab = vim.api.nvim_get_current_tabpage()
  local r = record(cwd, opts.name or (opts.task and clean(opts.task:gsub('\n',' '),60)))
  r.tab = tab; vim.t[tab].spaceghost_name=r.name; S.creating = r
  local ok, s = pcall(require('agentic.session_registry').create, nil, { kind = 'new', cwd = function() return cwd end })
  S.creating = nil
  if not ok or not s then r.status='failed'; r.error=clean(s or 'Session creation failed'); event(r,r.error,'error'); return r end
  adopt(s,r)
  require('agentic.session_registry').show_session(r.session_key,{ auto_add_to_context=false })
  if opts.task and opts.task ~= '' then M.send(r.id,opts.task) end
  if opts.background and vim.api.nvim_tabpage_is_valid(origin) then vim.api.nvim_set_current_tabpage(origin) end
  event(r,'Worker created','start'); arm(); return r
end
-- Observe before Agentic converts ACP rawInput/rawOutput into display blocks.
function M._raw(client, params)
  local r
  for _, item in ipairs(M.list()) do
    if item.session_id == params.sessionId and item._session and item._session.agent == client then r = item; break end
  end
  if not r or type(params.update) ~= 'table' then return end
  local u = params.update; local kind = u.sessionUpdate
  if kind == 'tool_call' or kind == 'tool_call_update' then
    local id = tostring(u.toolCallId or '')
    if id == '' then return end
    local t = r.tools[id]
    if not t then
      local count=0; for _ in pairs(r.tools) do count=count+1 end
      if count >= LIMIT.tools then
        local oldest; for k,v in pairs(r.tools) do if not oldest or v.at < r.tools[oldest].at then oldest=k end end
        r.tools[oldest]=nil
      end
      t={id=id}; r.tools[id]=t
    end
    t.title=clean(u.title or t.title); t.status=clean(u.status or t.status); t.kind=u.kind or t.kind; t.at=os.time()
    -- Retain bounded summaries rather than arbitrary tool output or credentials.
    local input, output = u.rawInput, u.rawOutput
    t.input = input and clean(type(input)=='string' and input or vim.inspect(input),2048) or t.input
    t.output = output and clean(type(output)=='string' and output or vim.inspect(output),2048) or t.output
    local child_id
    if type(output)=='table' then child_id=output.agent_id or output.agentId or output.thread_id end
    if type(input)=='table' then child_id=child_id or input.agent_id or input.agentId or input.receiver_thread_id end
    local meta = u._meta
    if type(meta)=='table' then
      local collab=meta.collaboration or meta.codex or meta
      if type(collab)=='table' then child_id=child_id or collab.agent_id or collab.agentId or collab.receiver_thread_id end
    end
    local child_ids = {}
    if child_id then child_ids[1]=child_id end
    if type(input)=='table' then
      if input.agentThreadId then child_ids[#child_ids+1]=input.agentThreadId end
      for i,child in ipairs(type(input.receiverThreadIds)=='table' and input.receiverThreadIds or {}) do
        if i>LIMIT.children then break end
        child_ids[#child_ids+1]=child
      end
    end
    for _,child in ipairs(child_ids) do
      local key=clean(child,120); local count=0; for _ in pairs(r.children) do count=count+1 end
      if r.children[key] or count < LIMIT.children then
        local state=type(input)=='table' and type(input.agentsStates)=='table' and input.agentsStates[child]
        local child_status=type(state)=='table' and state.status or type(state)=='string' and state or t.status
        local prior=r.children[key]
        r.children[key]={id=key,name=clean(type(input)=='table' and (input.prompt or input.message or input.agentPath) or prior and prior.name or t.title,120),status=clean(child_status,120),at=os.time(),via='parent',tool_id=id}
      end
    end
    if type(u.locations)=='table' then for i,loc in ipairs(u.locations) do if i>128 then break end; if loc.path and (u.kind=='edit' or t.kind=='edit') then changed_file(r,loc.path) end end end
    r.status='working'; r.activity=t.title ~= '' and t.title or 'Running tool'
    if kind=='tool_call' then event(r,r.activity,'tool') else notify() end
  elseif kind == 'plan' then
    r.plan={}; for i,entry in ipairs(u.entries or {}) do if i>100 then break end; r.plan[#r.plan+1]={content=clean(entry.content,1024),status=clean(entry.status,64),priority=entry.priority} end
    event(r,'Plan updated','plan')
  elseif kind == 'usage_update' then
    r.usage={used=u.used,size=u.size}; notify()
  elseif kind == 'current_mode_update' then
    r.mode=clean(u.currentModeId,120)
  elseif kind == 'agent_thought_chunk' then
    r.status='thinking'; r.activity='Thinking'; notify()
  elseif kind == 'agent_message_chunk' then
    r.status='working'; r.activity='Writing response'; notify()
  elseif kind == 'session_info_update' and u.title then
    r.session_title=clean(u.title,120)
  end
  if r._stopping then r.status='stopping'; r.activity='Stopping turn' end
  if r._replaying then r.status='starting'; r.activity='Restoring session' end
end
function M._hook(name, data)
  local r=lookup(data or {}); if not r then return end
  if data.session_id then r.session_id=data.session_id end
  if name=='on_prompt_submit' then
    if not r._dispatching then r._active_peer=nil end
    r.status='thinking'; r.activity='Thinking'; r.started_at=os.time(); r.finished_at=nil; event(r,'Turn started','prompt'); arm()
  elseif name=='on_response_complete' then
    local stopped=r._stopping; r._stopping=nil
    r.status=data.success==false and 'failed' or 'done'; r.finished_at=os.time(); r.activity=data.success==false and 'Turn failed' or 'Turn complete'
    if stopped then r.status='done'; r.activity='Turn stopped' end
    r.error=data.error and clean(type(data.error)=='table' and data.error.message or data.error) or nil
    event(r,r.activity,data.success==false and 'error' or 'done'); arm()
  elseif name=='on_request_permission' then
    if not r._stopping then r.status='waiting'; r.activity='Approval requested'; event(r,r.activity,'permission') end
  elseif name=='on_file_edit' then
    local path=data.filepath or data.file_path or data.path; if path then changed_file(r,path) end
  elseif name=='on_create_session_response' then
    local response=data.response or {}; r.model=response.models and response.models.currentModelId or r.model
  end
end
function M.attach()
  if not package.loaded['agentic'] then return false end
  local Registry=require('agentic.session_registry')
  local Manager=require('agentic.session_manager')
  local Client=require('agentic.acp.acp_client')
  local Hooks=require('agentic.utils.hooks')
  if type(Manager._handle_input_submit)=='function' then
    wrap(Manager,'_handle_input_submit',function(original)
      return function(self,text,...)
        local r=S.records[self._spaceghost_worker_id]
        if r and not r._dispatching and not text:match('^/new%s') and text~='/new' then
          if self.is_generating or pending(r) or r._stopping or not self.session_id or #r.queue>0 then
            local msg,err=S.api.send(r.id,text)
            if not msg then vim.notify(err,vim.log.levels.WARN) end
            return msg~=nil
          end
          r._active_peer=nil
        end
        return original(self,text,...)
      end
    end)
  end
  local Agentic=require('agentic')
  if type(Agentic.stop_generation)=='function' then
    wrap(Agentic,'stop_generation',function(original)
      return function(...)
        local current=Registry.current and Registry.current()
        local r=current and S.records[current._spaceghost_worker_id]
        if r then return S.api.stop(r.id) end
        return original(...)
      end
    end)
  end
  wrap(Manager,'prepare_start',function(original)
    return function(self,spec,...)
      local r=adopt(self,S.creating)
      -- Resolve once, before when_ready can resume in another tab/workspace.
      if not S.creating then
        local ok,cwd=pcall(function() return spec.cwd and spec.cwd() or require('agentic.config').acp_configs.session_cwd() end)
        if ok and type(cwd)=='string' then r.cwd=cwd; r._workspace_captured=true end
      end
      local handlers,err=original(self,spec,...)
      if handlers then
        handlers._spaceghost_worker_id=r.id
        if spec.kind=='load' then
          r.session_id=spec.session_id; r._replaying=true; r.activity='Restoring session'
        end
        self:on_session_ready(function()
          if S.records[r.id]~=r or session(r)~=self then return end
          r.session_id=self.session_id; r._replaying=nil; r.status='ready'
          event(r,'Session ready','ready'); S.api.tick()
        end,function()
          if S.records[r.id]~=r then return end
          r._replaying=nil; r._fatal=true; r.status='failed'; r.error='Session startup failed'
          clear_queue(r,'failed'); event(r,r.error,'error')
        end)
        arm()
      end
      return handlers,err
    end
  end)
  local function contextual(original, self, id, ...)
    local previous=self._spaceghost_start_id; self._spaceghost_start_id=id
    local results={pcall(original,self,...)}
    self._spaceghost_start_id=previous
    if not results[1] then error(results[2]) end
    return unpack(results,2)
  end
  wrap(Client,'create_session',function(original)
    return function(self,handlers,callback,cwd)
      return contextual(original,self,handlers._spaceghost_worker_id,handlers,callback,cwd)
    end
  end)
  wrap(Client,'load_session',function(original)
    return function(self,id,cwd,servers,handlers,callback)
      local r=S.records[handlers._spaceghost_worker_id]
      if r then r.session_id=id; r._replaying=true end
      return contextual(original,self,handlers._spaceghost_worker_id,id,cwd,servers,handlers,callback)
    end
  end)
  wrap(Client,'_send_request',function(original)
    return function(self,method,params,callback,...)
      local r=S.records[self._spaceghost_start_id]
      if method=='session/prompt' then
        for _,item in ipairs(S.api.list()) do
          if item.session_id==params.sessionId and item._session and item._session.agent==self then
            item._prompt_epoch=(item._prompt_epoch or 0)+1
            local epoch,cb,completed=item._prompt_epoch,callback,false
            callback=function(...)
              -- A delayed/duplicate response must never clear a newer turn's
              -- is_generating flag in SessionManager's scheduled callback.
              if completed or S.records[item.id]~=item or item._prompt_epoch~=epoch then return end
              completed=true
              if cb then return cb(...) end
            end
            break
          end
        end
      end
      if r and (method=='session/new' or method=='session/load') then
        params=vim.deepcopy(params); params.cwd=r.cwd; params.mcpServers=params.mcpServers or {}
        local ok,descriptor=pcall(function() return require('spaceghost.worker_bus').descriptor(r.id) end)
        if ok and descriptor then params.mcpServers[#params.mcpServers+1]=descriptor; r.bridge=true
        else r.bridge=false; event(r,'Peer bridge unavailable: '..clean(descriptor),'error') end
        local cb=callback
        callback=function(result,err)
          if S.records[r.id]==r then
            if result then r.session_id=result.sessionId or params.sessionId or r.session_id end
            if err then r.status='failed'; r._fatal=true; r.error=clean(type(err)=='table' and err.message or err); event(r,r.error,'error') end
          end
          if cb then return cb(result,err) end
        end
      end
      return original(self,method,params,callback,...)
    end
  end)
  wrap(Client,'__handle_session_update',function(original)
    return function(self,params,...)
      pcall(S.api._raw,self,params)
      return original(self,params,...)
    end
  end)
  wrap(Hooks,'invoke',function(original)
    return function(name,data,...)
      -- Upstream user hooks remain intact, including hooks configured after attach.
      local result=original(name,data,...)
      pcall(S.api._hook,name,data)
      return result
    end
  end)
  for _,s in pairs(Registry.sessions or {}) do
    if not s._destroyed and not (s._spaceghost_worker_id and not S.records[s._spaceghost_worker_id]) then
      local r=adopt(s)
      if s.session_id and r.status=='starting' then r.status=s.is_generating and 'thinking' or 'ready' end
    end
  end
  M.tick(); return true
end
function M.setup()
  local group=vim.api.nvim_create_augroup('SpaceghostWorkers',{clear=true})
  vim.api.nvim_create_autocmd('TabClosed',{group=group,callback=function() vim.schedule(function() S.api.tick() end) end})
  vim.api.nvim_create_autocmd('VimLeavePre',{group=group,callback=function()
    if S.timer then S.timer:stop(); S.timer:close(); S.timer=nil end
  end})
end
return M
