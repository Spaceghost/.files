-- Run: nvim --headless -u NONE -l tests/nvim-workers.lua
vim.opt.rtp:prepend(vim.fn.getcwd() .. '/.config/nvim')
local sessions, starts, requests = {}, {}, {}
local Client = {}
function Client:_send_request(method, params, cb) requests[#requests+1] = {method=method,params=params,cb=cb} end
function Client:create_session(h, cb, cwd) self:_send_request('session/new',{cwd=cwd(),mcpServers={}},cb) end
function Client:load_session(id,cwd,servers,h,cb) self:_send_request('session/load',{cwd=cwd,mcpServers=servers},cb) end
function Client:__handle_session_update(p) self.forwarded=p end
local client = setmetatable({}, {__index=Client})
local Manager = {}
function Manager:prepare_start() return {} end
function Manager:_handle_input_submit(text) assert(not self.is_generating); self.is_generating=true; self.prompts=self.prompts or {}; table.insert(self.prompts,text); return true end
local Registry={sessions=sessions}
function Registry.get(k) return sessions[k] end
function Registry.create(_,spec)
 local s=setmetatable({session_key=#starts+1,agent=client,permission_manager={has_pending=function() return false end},widget={get_visible_tab_id=function() return nil end}}, {__index=Manager})
 sessions[s.session_key]=s; starts[#starts+1]=s
 function s:on_session_ready(cb,fail) self.ready=cb; self.fail=fail end
 local h=s:prepare_start(spec); s.handlers=h
 s.start=function()
  local complete=function(r) s.session_id=r.sessionId or spec.session_id; s.ready(s) end
  if spec.kind=='load' then client:load_session(spec.session_id,spec.cwd(),{},h,complete)
  else client:create_session(h,complete,spec.cwd) end
 end
 return s
end
function Registry.show_session() end
package.loaded['agentic']={}
package.loaded['agentic.session_registry']=Registry
package.loaded['agentic.session_manager']=Manager
package.loaded['agentic.acp.acp_client']=Client
package.loaded['agentic.utils.hooks']={invoke=function() end}
package.loaded['spaceghost.worker_bus']={descriptor=function(id) return {name=id} end,revoke=function() end}
local W=require('spaceghost.workers'); W.setup(); W.attach()
local a=W.new({cwd='/var/home/jack',task='first',background=true})
local b=W.new({cwd='/var/tmp',background=true})
assert(a.id~=b.id and a.tab~=b.tab,'stable distinct workers/tabs')
starts[2].start(); starts[1].start()
assert(requests[1].params.cwd=='/var/tmp' and requests[2].params.cwd=='/var/home/jack','captured cwd')
assert(requests[1].params.mcpServers[1].name==b.id,'per-attempt bridge identity')
requests[2].cb({sessionId='one'}); requests[1].cb({sessionId='two'})
W.tick(); assert(starts[1].prompts[1]=='first')
local m=assert(W.peer(b.id,a.id,'hello')); W.tick(); assert(#starts[1].prompts==1 and m.status=='queued')
starts[1].is_generating=false; W.tick(); assert(#starts[1].prompts==2 and m.status=='delivered')
starts[1].permission_manager.has_pending=function() return true end
starts[1].is_generating=false; assert(W.send(a.id,'hold')); W.tick(); assert(#starts[1].prompts==2)
assert(not W.peer(a.id,b.id,string.rep('x',20000)))
client:__handle_session_update({sessionId='one',update={sessionUpdate='tool_call',toolCallId='t',title='spawn_agent',rawInput={agent_id='child',message='inspect'}}})
assert(a.tools.t and a.children.child and client.forwarded,'raw telemetry and forwarding')
local old=a.id; package.loaded['spaceghost.workers']=nil; W=require('spaceghost.workers'); W.attach(); assert(W.get(old)==a,'reload persistence')
local wrapped=Client._send_request; W.attach(); assert(Client._send_request==wrapped,'idempotent wrappers')
client:__handle_session_update({sessionId='one',update={sessionUpdate='tool_call',toolCallId='legacy',title='spawnAgent',rawInput={prompt='Inspect lifecycle',receiverThreadIds={'legacy-child'},agentsStates={['legacy-child']={status='running'}}}}})
assert(a.children['legacy-child'].status=='running','installed adapter legacy collaboration shape')
local h=starts[2].handlers
client:load_session('restored','/wrong',{},h,function() end)
assert(requests[3].params.cwd=='/var/tmp' and requests[3].params.mcpServers[1].name==b.id,'restored session tools and captured cwd')
local inferred=assert(W.peer(a.id,b.id,'implicit reply'))
assert(inferred.reply_to==m.id and inferred.hops==2,'active delivered message supplies implicit hop context')
local reply=assert(W.peer(a.id,b.id,'reply',{reply_to=m.id}))
for hop=3,8 do
 local from=hop%2==1 and b.id or a.id
 local to=hop%2==1 and a.id or b.id
 reply=assert(W.peer(from,to,'continue',{reply_to=reply.id}))
end
assert(not W.peer(b.id,a.id,'too far',{reply_to=reply.id}),'bounded conversation hops')
for _=1,40 do W.send(a.id,'bounded') end
assert(#a.queue==32 and not W.send(a.id,'overflow'),'bounded queue')
-- A cancellation notification is not the outstanding prompt response.
local c=W.new({cwd='/var/home/jack',background=true})
starts[3].start(); requests[#requests].cb({sessionId='three'})
assert(W.send(c.id,'old turn')); W.tick()
local cs=starts[3]
local hooks=require('agentic.utils.hooks')
client:_send_request('session/prompt',{sessionId='three'},function()
 cs.is_generating=false
 hooks.invoke('on_response_complete',{session_key=c.session_key,session_id='three',success=true})
end)
local old_completion=requests[#requests].cb
function client:stop_generation() self.cancel_requested=true end
function cs.permission_manager:clear() self.cleared=true end
local cancelled=assert(W.send(c.id,'cancel queued'))
assert(cs:_handle_input_submit('native while busy') and #cs.prompts==1,'native busy submission is queued')
assert(W.stop(c.id)); assert(cs.is_generating and c.status=='stopping' and cancelled.status=='cancelled','stop preserves generation gate')
local followup=assert(W.send(c.id,'after cancellation'))
W.tick(); assert(#cs.prompts==1 and followup.status=='queued','no prompt before cancellation acknowledged')
old_completion({}); W.tick()
assert(#cs.prompts==2 and cs.is_generating and followup.status=='delivered','acknowledgement releases next prompt')
old_completion({}); W.tick()
assert(cs.is_generating and c.status~='done','duplicate old completion cannot unlock newer generation')
assert(cs:_handle_input_submit('native while generating') and #cs.prompts==2,'native submission serialized after cancel')
cs.is_generating=false; W._hook('on_response_complete',{session_key=c.session_key,success=false,error='recoverable'})
assert(W.send(c.id,'retry after turn error'),'healthy failed turn accepts retry')
cs.permission_manager.has_pending=function() return true end
assert(cs:_handle_input_submit('native while waiting')); W.tick()
assert(#cs.prompts==2,'native permission submission remains queued')
local fixed=b.tab
vim.api.nvim_set_current_tabpage(fixed); vim.cmd('tabmove 0'); assert(b.tab==fixed,'tab handle survives reordering')
vim.cmd('tabclose'); W.tick(); assert(b.tab==nil and W.get(b.id)==b,'tab close retains session and inbox')
sessions[b.session_key]=nil; W.tick(); assert(b.status=='failed' and not W.send(b.id,'destroyed'),'destroyed destination rejected')
local timer=W.state().timer
package.loaded['spaceghost.workers']=nil; W=require('spaceghost.workers'); W.setup(); W.attach()
assert(W.state().timer==timer,'one persistent lifecycle timer')
-- Catch routing that accidentally depends on tab numbers under a large workspace.
local many={}
for i=1,40 do
 local worker=assert(W.new({cwd='/var/tmp',name='Stress '..i,task='task '..i,background=true}))
 local manager=starts[#starts]
 manager.start(); requests[#requests].cb({sessionId='stress-'..i})
 many[i]={worker=worker,manager=manager}
end
for i,item in ipairs(many) do
 local worker,manager=item.worker,item.manager
 assert(manager.prompts[1]=='task '..i,'initial prompt crossed workers')
 vim.api.nvim_set_current_tabpage(worker.tab); vim.cmd('tabmove 0')
 if i%3==0 then vim.cmd('tabclose') end
 assert(W.send(worker.id,'followup '..i))
 manager.is_generating=false
end
W.tick()
for i,item in ipairs(many) do
 assert(item.manager.prompts[2]=='followup '..i,'followup crossed workers after tab changes')
 if i%3==0 then
  assert(item.worker.tab==nil,'closed stress tab retained a stale handle')
  assert(W.open(item.worker.id))
  assert(vim.api.nvim_tabpage_is_valid(item.worker.tab),'closed worker view did not reopen')
 end
end
print('PASS 40 workers preserve prompt routing through tab reordering, closure and reopening')
W._hook('on_file_edit',{session_key=a.session_key,filepath='/var/tmp/edited.lua'})
assert(a.changed_files['/var/tmp/edited.lua'],'installed Agentic filepath hook was ignored')
-- Ordinary chat/restore entry points bypass workers.new and must still reconcile.
W.state().timer:stop(); W.state().timer:close(); W.state().timer=nil
local native=Registry.create(nil,{kind='new',cwd=function() return '/var/tmp' end})
local native_worker=W.get(native._spaceghost_worker_id)
assert(W.state().timer,'ordinary Agentic creation did not start lifecycle reconciliation')
native.start(); requests[#requests].cb({sessionId='native-entry'})
assert(native_worker.status=='ready','ordinary Agentic session remained starting after readiness')
local restored=Registry.create(nil,{kind='load',session_id='restore-history',cwd=function() return '/var/tmp' end})
local restored_worker=W.get(restored._spaceghost_worker_id)
restored.start()
client:__handle_session_update({sessionId='restore-history',update={sessionUpdate='plan',entries={{content='Saved plan',status='completed'}}}})
client:__handle_session_update({sessionId='restore-history',update={sessionUpdate='tool_call',toolCallId='saved-tool',title='Saved tool',status='completed'}})
assert(restored_worker.plan[1] and restored_worker.tools['saved-tool'],'restore replay before load response was lost')
assert(restored_worker.status=='starting','historical tool replay made an idle restore look active')
requests[#requests].cb({})
assert(restored_worker.status=='ready','restored session remained starting after readiness')
local legacy={session_key='legacy',session_id='legacy-session',widget={get_visible_tab_id=function() return nil end}}
sessions.legacy=legacy; W.attach()
assert(W.get(legacy._spaceghost_worker_id).cwd==nil,'migration invented a workspace for an existing session')
local migrated=W.get(legacy._spaceghost_worker_id)
migrated.cwd='/unproven/old/editor/cwd'; migrated._workspace_captured=nil
W.attach()
assert(migrated.cwd==nil,'reload retained a workspace invented by the previous tracker')
print('PASS native startup, restore replay, installed edit hooks and honest migration workspace')
local legacy_wrapper=Client._send_request
W.state().wrappers[legacy_wrapper]=true
package.loaded['spaceghost.workers']=nil; W=require('spaceghost.workers'); W.attach()
assert(Client._send_request~=legacy_wrapper,'live reload did not upgrade legacy wrapper behavior')
local upgraded=Client._send_request; W.attach()
assert(Client._send_request==upgraded,'live upgrade stacked another wrapper')
local upgrade_worker=assert(W.new({cwd='/var/tmp',background=true}))
starts[#starts].start()
assert(#requests[#requests].params.mcpServers==1,'live wrapper upgrade duplicated MCP injection')
requests[#requests].cb({sessionId='wrapper-upgrade'})
assert(upgrade_worker.status=='ready','upgraded wrapper lost readiness callback')
print('PASS live wrapper upgrades replace behavior without stacking requests')
local first_read=assert(W.peer(a.id,upgrade_worker.id,'first unread'))
assert(W.peer(a.id,upgrade_worker.id,'second unread'))
W.open(upgrade_worker.id)
assert(upgrade_worker.unread==2,'opening chat marked undisplayed inbox messages read')
assert(W.read(upgrade_worker.id,{first_read.id})==1 and upgrade_worker.unread==1,'visible-message read count is incorrect')
assert(W.read(upgrade_worker.id,{first_read.id,'missing'})==0 and upgrade_worker.unread==1,'duplicate reads changed unread count')
for i=1,101 do
 starts[#starts].is_generating=false; W.tick()
 assert(W.peer(a.id,upgrade_worker.id,'retained '..i))
end
assert(#upgrade_worker.inbox==100 and upgrade_worker.unread==100,'evicted messages left unreachable unread counts')
print('PASS inbox reads track inspected messages and exclude evicted unread entries')
print('worker lifecycle tests passed')
vim.cmd('qa!')
