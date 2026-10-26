# Codex Workers Implementation Plan

> Execute the independent components with superpowers:subagent-driven-development; integrate and verify in this session. User approved the design and execution; do not ask another approval question.

**Goal:** Deliver the approved animated native Neovim worker dashboard, multiple worker tabs, peer messaging and delegated activity here and on bak.
**Architecture:** Agentic owns chat/permissions; a reload-persistent Lua worker controller owns lifecycle/telemetry/queues. Native Lua dashboard consumes its public interface. A Lua stdio MCP helper forwards bounded JSON requests through a private vim.uv Unix socket to the owning Neovim instance.
**Tech Stack:** Lua, Neovim vim.uv/extmarks/buffers/tab handles, existing pinned Agentic/Codex ACP.
**Spec:** docs/superpowers/specs/2026-10-25-codex-workers-design.md

## Constraints

- Author code and tests only in Lua or Nelua; no new runtime dependencies.
- Preserve existing sessions, approvals, shell jobs, navigation and bak's unrelated changes.
- Stable worker identities, captured per-start workspaces, one widget per worker/tab, no concurrent prompts for a worker.
- Real plan/context progress only; bounded logs/inboxes/queues, local authenticated peer bridge, configurable animation.
- Source/configuration changes belong to .files and must be verified, committed, pushed and deployed on both machines.

## Shared interfaces

`spaceghost.workers`: setup(), attach(), list()->records[], get(id)->record|nil, new({task?,name?,cwd?,background?})->record, open(id), send(id,text,opts?)->message|nil,error, peer(from,to,text,opts?)->message|nil,error, stop(id), rename(id,name), dismiss(id), summary()->counts, subscribe(key,callback), tick(), state().

Record: id,name,cwd,session_key,session_id,tab,status,activity,started_at,finished_at,last_at,plan(entries array),usage({used,size}),model,changed_files(path-keyed set),tools(id-keyed map),children(id-keyed map),inbox(array),queue(array),unread,bridge,events(array of {at,text,kind}),error. All times are os.time() seconds. Unknown fields may be nil. Status: starting/ready/thinking/working/waiting/stopping/done/failed. summary: total,running,waiting,done,failed,unread.

`spaceghost.worker_bus`: ensure()->socket path, descriptor(worker_id)->ACP MCP server definition, revoke(worker_id), close(). Tools: workers_list, workers_status, workers_send(worker_id,message,reply_to?), workers_inbox. Peer tools are bound to their authenticated caller, never a caller-supplied sender ID.

`spaceghost.worker_ui`: setup(), open(), close(), statusline()->escaped statusline fragment. UI calls workers APIs above; setup subscribes under a stable key and rebinds commands idempotently. Motion controlled by vim.g.spaceghost_worker_motion (false disables). UI setup occurs during config init, engine attach only when Agentic loads.

## Task 1: worker lifecycle and events

- [x] Implement workers.lua and Lua lifecycle tests: stable IDs, concurrent async starts in different workspaces, fixed tab handles, queue serialization with permissions/generation checks, bounded peer messages/hop chains, raw tool and child telemetry, hook composition and reload-safe timer/subscriptions.
- [x] Verify offline Lua tests and real two-session Agentic integration; preserve existing sessions during adoption.

## Task 2: dashboard and native visual integration

- [x] Implement worker_ui.lua with wide/narrow views, animated spinners/sweeps, plan/context bars, detail/timeline/inbox/children, keyboard controls and existing palette. Add scoped Worker highlights; integrate keys/menu/statusline/init without changing existing chat behavior.
- [x] Test keyboard/narrow/many-record views, stable selection and animation cleanup. No global redraw loop when views are hidden.

## Task 3: Lua MCP peer transport

- [x] Implement worker_bus.lua and agentic/worker-mcp.lua using bounded JSONL and vim.uv, private socket/token identity, timeouts, lifecycle cleanup, and new/load request injection through Task 1's wrappers.
- [x] Test real stdio MCP initialization/tool calls, identity isolation, malformed/oversized frames, dead sockets, and ordered busy-recipient delivery using Lua.

## Task 4: integration, review and rollout

- [x] Compose all modules, enhance chat headers, document controls and peer tool use, and run real multiworker/message/child activity checks and existing navigation regressions.
- [ ] Independent code review; fix significant issues with regressions. Verify running cockpit reload, commit/push, fast-forward bak preserving its edits, run checks there and reload without restarting jobs.

## Review focus

Simultaneous callbacks misbinding workspace/identity; duplicate prompt delivery during streaming/approvals; tab closure or reordering moving the wrong chat; full bak /tmp (use cache temp dirs); stale wrappers/timers after reload. Each receives explicit lifecycle or integration checks.

## Progress

- Design approved. User's Lua/Nelua-only constraint incorporated before implementation.
- Local verification: real parallel Codex sessions, real MCP peer discovery/send/automatic delivery and native delegated child activity all passed. Dashboard tests virtualize 80 workers and exercise narrow layouts, keyboard controls and motion/reload behavior. Existing navigation and native terminal launch checks pass.
- Independent transport review found oversized successful-send responses and unreadable large inboxes; compact receipts and byte-budgeted pagination fix these with real stdio regressions.
- Independent full review found cancellation/native-submit concurrency and recoverable-error retry issues; queue ownership now survives cancellation until acknowledgment, native submissions share the queue, stale responses are ignored and healthy sessions can retry. Delayed-cancel/native-input/error regressions pass.
- Integration fixes: defer/coalesce redraws and skip detached/headless redraws; replace the HUD timer on reload; escape worker/model text in tabline/winbar; cancel pending terminal insert mode on dashboard entry. Each has a reproducing integration check.
- Full detail navigation retains every reported plan step, inbox message and delegated child, with cached Unicode wrapping and viewport-only rendering. A 40-worker lifecycle harness exercises tab reordering, closure, reopening and prompt routing; the public CodexNew command is covered against real installed Agentic sessions.
- bak passed real peer messaging and delegated child tracking. SSH verification caught absent MYVIMRC; reload now uses the actual source config path and the remote reload regression passes.
