# Claude Code desktop notifications

Claude Code 2.1.263 exposes supported lifecycle hooks for the local terminal
session. `oldbook-claude-notify` reads one hook payload from standard input and
emits only these content-free desktop notifications:

| Hook | Accepted detail | Desktop notification |
| --- | --- | --- |
| `PermissionRequest` | any tool permission request | critical `Claude • Waiting on you` |
| `Notification` | `permission_prompt` | normal `Claude • Needs attention` |
| `Notification` | `idle_prompt` | normal `Claude • Needs attention` |
| `Notification` | `elicitation_dialog`, `elicitation_url_dialog` | normal `Claude • Needs attention` |
| `Notification` | `agent_needs_input` | normal `Claude • Needs attention` |
| `Notification` | `quota_auto_resume_stale`, `quota_auto_resume_disabled` | normal `Claude • Needs attention` |
| `Stop` | both background-work arrays are present and empty | normal `Claude • Done` |
| `UserPromptSubmit` | any | none; clears routing metadata only |

The helper invokes `notify-send` with `--app-name=Claude`. It never forwards the
hook's message, title, prompt, answer, assistant response, tool name, tool input,
path, transcript location, task description, authentication data, or model data.
It never writes to standard output or standard error. In particular, a
`PermissionRequest` invocation emits no `allow` or `deny` decision, and a `Stop`
invocation emits no `block` decision. Notification failure therefore cannot
answer a prompt, alter tool input, add model context, or restart Claude's loop.

Both permission signals are registered because a sandboxed command's network
request does not produce `PermissionRequest`; only `permission_prompt` covers
that case. An ordinary tool permission request first produces the immediate
`PermissionRequest` hook and can produce a second notification about six seconds
later when the user remains away. This possible duplicate is content-free and
extends the attention indication without changing the pending request; the
routing record below closes the earlier popup when the second one arrives, so
Jack never has two live notifications open for the same wait.

## Auto-dismiss and click-to-jump routing

A waiting-on-you event (`PermissionRequest`, or an attention-listed
`Notification`) also writes a private routing record to
`$XDG_RUNTIME_DIR/oldbook/claude-events/<sha256(session_id)>.json`, mirroring
`oldbook-codex-notify`'s record for Codex: the printed notification id, the
session's `TMUX_PANE`, its controlling tty, its `cwd`, which event produced it,
and a 300-second TTL. None of that reaches the visible banner text above --
the banner stays exactly as content-free as it always has. The record exists
only for two private consumers:

- `oldbook-claude-notify` itself, on the next `Stop` or `UserPromptSubmit` for
  that same session: both are positive evidence the wait is over (the turn
  finished, or Jack typed something back into that exact session), so both
  call `org.freedesktop.Notifications.CloseNotification` on the recorded id
  over the session bus and delete the record -- whether or not `Stop` also
  sends its own low-urgency `Claude • Done` notice.
- `oldbook-claude-notify-focus`, wired in `~/.config/swaync/config.json` as
  the `claude-focus` script (ahead of the generic `focus-sender` fallback, so
  swaync's "only the first matching script runs" rule always picks it for a
  `Claude` notification). It resolves the record swaync's `SWAYNC_ID` points
  at, or the newest live one if that id is missing or already gone, and finds
  or reattaches the session: focus the live Sway window when the pane is
  already visible somewhere, using the same tty/tmux-pane matching
  `oldbook-notification-led` trusts for Codex; otherwise select that pane in
  tmux and open a terminal attached to its session, the same
  `tmux attach-session` pattern `oldbook-agents attach` uses. Landing
  anywhere closes the notification and deletes the record the same way `Stop`
  does, so visiting the session also makes its notification go away.

Neither consumer answers a prompt, alters tool input, or otherwise changes
Claude's behaviour; both only ever close a desktop notification and delete a
file this helper itself wrote.

`agent_completed`, `SubagentStop`, `TaskCompleted`, `SubagentStart`,
`TaskCreated`, and session-start events are excluded. A main-agent `Stop` payload
with a missing or nonempty `background_tasks` or `session_crons` array is also
ignored because the official schema says those arrays distinguish a completed
session from one paused for work that will wake it again. The normal completion
alert therefore requires positive evidence that no background work is active.
The installed 2.1.263 emitter was checked directly: it always constructs both
arrays for every main-agent `Stop`, and its serializers return empty arrays when
nothing is active. Although its compatibility schema permits these fields to be
absent, an ordinary completion from this installed build satisfies the check.

## Installation and recovery

Deploy the HOME overlay, review the installer, then run:

```sh
~/.files/alpine/bin/install-claude-notifications
```

The installer parses only `~/.claude/settings.json`. It preserves every
top-level setting and existing hook group, then appends four exact command-hook
groups under `PermissionRequest`, `Notification`, `Stop`, and
`UserPromptSubmit`. It neither reads nor modifies project settings,
transcripts, credentials, sessions, or other Claude files. Existing exact
handlers are not duplicated.

The click side lives outside `~/.claude/settings.json`: `oldbook-claude-notify-focus`
is a plain script under `~/.local/bin`, wired as the `claude-focus` entry in
`~/.config/swaync/config.json` (see "Auto-dismiss and click-to-jump routing"
above). The installer does not touch swaync's config; that file is part of the
ordinary desktop overlay like the rest of `~/.config`.

Before replacement, it writes an exact mode-0600 copy and a hash manifest under
the private directory
`~/.local/state/oldbook/claude-notifications/backups/<timestamp>/`. The original
settings mode is preserved. Roll back before making later settings changes:

```sh
~/.files/alpine/bin/install-claude-notifications \
  --rollback ~/.local/state/oldbook/claude-notifications/backups/<timestamp>
```

Rollback checks that the installed settings still match the manifest, restores
the exact original bytes and mode, or removes `settings.json` if installation
created it. It refuses malformed JSON, non-regular settings targets, changed
installed settings, and changed backup copies.

Claude Code normally picks up direct settings edits through its file watcher, so
an active session does not require a restart. Open the read-only `/hooks` browser
after installation to verify the four command definitions. If they do not
appear, restart that CLI session and check `/hooks` again. Interactive sessions
hold all settings hooks until the current workspace has been trusted.

## Browser limit

These hooks belong to local Claude Code sessions. They do not observe activity
in a regular `claude.ai` browser tab. Anthropic documents native computer
notifications for Claude in Chrome and Cowork when the extension's notification
permission is enabled. Those browser-generated desktop notifications may be
visible to the separate D-Bus notification monitor, but their application name
and payload are browser controlled and are outside this helper's contract.

## References

- [Claude Code hooks guide and Linux notification example](https://code.claude.com/docs/en/hooks-guide#get-notified-when-claude-needs-input)
- [Claude Code `PermissionRequest` hook](https://code.claude.com/docs/en/hooks#permissionrequest)
- [Claude Code notification types and timing](https://code.claude.com/docs/en/hooks#notification)
- [Claude Code `Stop` hook and background-work fields](https://code.claude.com/docs/en/hooks#stop)
- [Claude Code `UserPromptSubmit` hook](https://code.claude.com/docs/en/hooks#userpromptsubmit)
- [Claude in Chrome notification capability](https://support.claude.com/en/articles/12012173-get-started-with-claude-in-chrome)
