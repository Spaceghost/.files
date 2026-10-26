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
 s.start=function() client:create_session(h,function(r) s.session_id=r.sessionId; s.ready(s) end,spec.cwd) end
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
print('worker lifecycle tests passed')
vim.cmd('qa!')
