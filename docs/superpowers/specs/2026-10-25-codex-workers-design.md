# Native Codex worker dashboard

## Intent

Make Neovim a visibly active, easy-to-steer Codex workspace. The user wants a substantial UI improvement: spinners, animations, progress bars, and multiple workers with useful information at a glance. They selected **both independent sessions and delegated child workers, independent sessions first**. Keep the existing Agentic chat, authentication, theme, file context and review experience.

## Recommended approach

Extend the existing pinned Agentic installation with native Lua buffers, windows, extmarks and a live event model. Agentic remains responsible for chat, approvals and edits; the dashboard adds orchestration, navigation and summaries. This avoids maintaining a separate Codex client and keeps current conversations usable.

Alternatives considered: styling only Agentic's chat would not provide a worker overview; replacing Agentic with a new app-server client would require rebuilding authentication, permissions and editing behavior that already work. Neither fits this incremental upgrade.

## Proposed layout

```text
 SPACEGHOST / CODEX WORKERS                 3 active  1 needs you
 ────────────────────────────────────────────────────────────────
 WORKERS                         SELECTED / build dashboard
 ⠹ build dashboard   WORKING      Current: update the worker cards
   ██████░░░░  3/5 plan steps     Workspace: ~/.files
   editing workers.lua · 02:14    Model: supplied by Codex
                                 Plan: 3 complete / 5 total
 ◆ review changes    NEEDS YOU    ████████████░░░░░░░░
   approval requested            Context: 24% used
   run navigation checks         ████░░░░░░░░░░░░░░░░
                                 Activity
 ✓ investigate API   DONE         21:14  reading session events
   4/4 steps · 01:32              21:15  editing worker cards
                                 Delegated workers
                                 ⠹ investigate layout
 ────────────────────────────────────────────────────────────────
 n new  Enter chat  p prompt  r rename  s stop  a delegate  q close
```

Layout adapts to terminal size: wide terminals show list and detail together;
narrow terminals show a compact list and a selected-worker detail view. The list
scrolls without a worker-count limit. Colors use the existing violet, mint,
amber, blue and alert palette. Labels accompany every color and symbol.

## Interaction

- `Ctrl-\ o`, `:CodexWorkers`, and the F4 Codex menu open the dashboard. Existing `Ctrl-\ i` keeps opening chat.
- Create a worker with a task prompt in the current workspace; give it a readable default name. Offer a different workspace explicitly when requested. Each worker's workspace stays fixed and visible.
- Select a worker to open its existing native chat, send a follow-up, rename it, or stop its current turn while preserving the conversation. Busy workers can receive a visibly queued follow-up. Selecting a waiting worker opens its existing permission UI.
- Creating or selecting a worker never destroys other sessions. Hiding the dashboard does not stop any work. Completed workers stay visible until dismissed.
- Each independent worker can have its own Neovim tab; many worker tabs can remain open concurrently. The dashboard can open or focus a selected worker's tab. Store session identity independently of tab number, so reordering or closing tabs cannot misroute messages or stop workers.
- A delegate action asks the selected parent to create child agents. Show delegated activity under its parent from real collaboration events. Interact through the parent when the installed client cannot address child sessions directly; label this clearly rather than pretending child activity is an independent chat.

## Peer discovery and messaging

The user additionally requires workers to know about one another and communicate.
Expose a local worker directory and messaging tools to each independent Codex
session through a small MCP bridge. Workers can list peer IDs, names, workspaces
and activity; send a peer a question or result; and inspect their own inbox.
The UI provides the same directory and inbox, with unread counts and sender names.

Messages go to a stable worker ID, never a tab number. Busy workers receive
messages in an ordered queue without concurrent prompts or interrupted tools.
Show queued/delivered state and preserve sender provenance in delivery prompts.
Deliver automatically to idle workers only after checking readiness, absence of
active generation and absence of pending approvals. The same per-worker queue
serializes UI follow-ups and peer messages; recheck worker identity and state
after every asynchronous boundary. Include sender and message IDs and a bounded
conversation hop count; do not synthesize automatic acknowledgement prompts.
Bound message sizes and queues, reject unknown/destroyed
destinations, and keep bridge access local to the owning Neovim instance.

Scope peer discovery to one running Neovim instance on one machine. Local and
bak each host their own worker group; a cross-machine relay is outside this
implementation. Delegated child agents remain under their parent unless the
installed adapter exposes an independently addressable child session.

## Activity and progress

Track starting, ready, thinking, working, waiting for approval, stopping, done and
failed states. Show elapsed turn time, last activity, model, workspace, changed
files and tool activity when available. Approval and failure states get the
highest visual priority; completions remain visibly marked until visited.

Use smooth spinner frames and an indeterminate activity sweep while busy. Show
determinate progress only for reported plan steps and context usage; never
invent a percentage or completion estimate for an open-ended agent task. Unknown
metrics appear as unavailable. Keep a bounded recent activity log per worker.

Add a compact running/waiting/done worker summary to the global statusline, so
background work remains visible while editing. Richer chat headers show the
selected worker's state, elapsed time and available usage. Motion is configurable
and can be disabled. Timers animate only visible surfaces and clean up on reload
or shutdown; hidden sessions continue through Agentic without redraw loops. Use
one coalesced dashboard timer, not an animation timer per tracked worker. Render
only the selected detail pane and visible list rows; stress-test dozens of worker
records and tabs, including closing/reordering tabs during activity.

## Integration and limitations

The installed Agentic version supports multiple independent sessions, session
hooks, plan/usage events, chat history/tool records, permission state and session
navigation. It currently does not negotiate native ACP child-session support.
Implement delegated visibility using the adapter's legacy collaboration events;
keep child controls routed through the parent. Do not advertise direct child
chat or complete subagent telemetry without actual protocol support.

Use a reload-persistent worker store and idempotent event subscriptions. Retain
existing sessions and shell jobs when reloading. Keep captured origin workspaces
stable through asynchronous session initialization and dashboard focus changes.
Agentic's current create-session method hardcodes an empty MCP server list:
add one version-checked, idempotent integration wrapper at the ACP request seam
for session/new and session/load. Bind each bridge identity and workspace to its
own start attempt, never a mutable global. Observe raw session updates before
Agentic converts tool calls, while forwarding every event unchanged to its normal
handler; ordinary session hooks alone do not receive tool/collaboration updates.

Respect Agentic's one-visible-widget-per-tab and one-tab-per-session invariant.
Keep Neovim tab handles, not tab numbers; focus the existing worker tab before
showing its widget. Closing a tab detaches the view and retains the session and
inbox. New/restored sessions receive peer tools; existing active sessions keep
running and display their bridge availability rather than being restarted.
Sanitize tool output for display, truncate long fields by display width and bound
stored event data. The pinned upstream package must remain unmodified.

## Delivery and verification

Implement independent workers and visual telemetry first, then delegated
activity and parent interaction. Verify simultaneous real Codex sessions,
background completion, peer discovery/messaging and busy-recipient queues,
tab creation/reordering/closure, follow-up routing, permission attention, event-driven
progress, narrow layouts, keyboard operation, disabled motion, stale callbacks,
timer cleanup and configuration reloads. Run existing navigation regressions.
Review before committing; push .files and deploy/reload locally and on bak,
preserving bak's unrelated changes and running terminals.

Estimated implementation and verification: 60–90 minutes, including peer tools.

## Builder review

Independent review found the design feasible with no additional user-owned
decisions. Incorporated its requirements for per-attempt MCP binding, raw tool
events, readiness/approval-aware prompt serialization, bounded peer conversations,
existing-session migration, tab handles and upstream visibility invariants.

## Approval

Approved by the user: "Dog do it." Additional constraint: author implementation
and tests only in Lua or Nelua. The MCP stdio helper therefore runs as a minimal
headless Neovim Lua process, using vim.uv pipes and a private local Unix socket;
no new Node/Python service or dependency is introduced. Existing Codex ACP
dependencies remain installed as before.
