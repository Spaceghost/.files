# Codex desktop notifications

Codex CLI 0.153.4 exposes the two required signals through supported local
interfaces. The top-level `notify` callback receives one JSON argument and
currently emits `agent-turn-complete`. A user hook receives `PermissionRequest`
on standard input when Codex is about to ask the user for approval. A
`UserPromptSubmit` hook clears transient routing metadata at the next prompt.

`mbp-intel-codex-notify` accepts only these invocations:

```text
mbp-intel-codex-notify --notify '<agent-turn-complete JSON>'
mbp-intel-codex-notify --hook                 # hook JSON on standard input
```

Completion adds a normal `Codex • Done` notification. An approval request adds
a critical `Codex • Needs attention` notification. There is no notification
body. The helper does not copy prompts, assistant output, commands, approval
reasons, paths, model names, transcript locations, authentication data, or API
data. It never writes to standard output, so the `PermissionRequest` hook does
not allow, deny, answer, or otherwise influence the approval. The callbacks use
the existing `notify-send` and SwayNC path. A new Codex notice adds its mapped
terminal window to the Caps Lock attention set. Focusing or closing that window
clears it; other unseen AI windows keep flashing. See
[AI attention behavior](2026-09-07-ai-attention-led.md).

## Transient routing contract

For a supported event with a session identifier, the helper atomically writes a
mode-0600 JSON file under this private directory:

```text
$XDG_RUNTIME_DIR/mbp-intel/codex-events/<sha256-session-id>.json
```

Schema version 1 contains exactly:

```json
{
  "version": 1,
  "event": "turn-complete",
  "observed_at": 1788800000,
  "valid_until": 1788800300,
  "tmux_pane": "%17",
  "tty": null
}
```

`event` is either `turn-complete` or `approval-requested`. `tmux_pane` is copied
only from a syntactically valid `TMUX_PANE` in the helper's own environment;
`tty` is discovered from the helper's own standard file descriptors or its own
Linux `/proc/self/stat` controlling-terminal number. The latter is necessary
because Codex deliberately redirects callback and hook standard streams. It
does not inspect a parent process. A consumer may use either value to offer a
jump to the terminal that originated the event. Both can be null.

The record describes a received event, never current agent state. It expires
after 300 seconds, expired files are removed on the next callback, and
`UserPromptSubmit` deletes the previous record for that session. Consumers must
ignore records after `valid_until`. No supported callback identifies a terminal
PID, and the helper does not inspect other processes or conversation logs to
invent one.

## Installation and recovery

Deploy the HOME overlay first, then run:

```sh
~/.files/alpine/bin/install-codex-notifications
```

The installer parses the existing TOML and JSON before changing anything. It
adds only the documented top-level `notify` command to `~/.codex/config.toml`
and notification-only `PermissionRequest` plus cleanup-only `UserPromptSubmit`
groups to `~/.codex/hooks.json`. Existing model, provider, plugin, authentication,
TUI, and hook settings remain present. Codex 0.153.4 reports the `hooks` feature
as stable and enabled, so the installer changes no feature flags.

Codex supports only one top-level `notify` command. If one is already configured,
the installer stops without modifying either file so the existing handler is not
silently replaced. The user can explicitly chain both handlers before retrying.
It likewise refuses malformed files, non-regular config targets, and unsafe
rollback state.

An exact private backup is created under
`~/.local/state/mbp-intel/codex-notifications/backups/`. The installer prints its
path. Roll back before making later Codex config changes:

```sh
~/.files/alpine/bin/install-codex-notifications \
  --rollback ~/.local/state/mbp-intel/codex-notifications/backups/<timestamp>
```

Rollback verifies that both installed files still match the recorded result,
then restores the exact originals or removes a file that did not previously
exist. It refuses to overwrite subsequent user changes.

Restart active Codex CLI processes after installation so they load the new
configuration. User hooks do not run merely because they exist: on the next
start, open `/hooks`, review the two exact command definitions, and trust them.
This hash-based trust is invalidated if the definitions change.

## Supported limits

The integration reports local Codex main-turn completion through
`agent-turn-complete` and actual Codex approval prompts through
`PermissionRequest`. `UserPromptSubmit` only clears an old routing event.
Malformed and unknown events are ignored, and desktop or record-write failures
cannot block Codex.

It does not infer a working state, approval resolution, subagent completion, or
browser activity. In particular, a ChatGPT browser tab title or process identity
does not provide a supported completion/approval signal, so ChatGPT web sessions
can be named and focused but cannot receive these completion badges from this
helper.

## References

- [Advanced Codex configuration: notifications](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications)
- [Codex configuration reference: `notify`](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codex hooks, trust, and lifecycle events](https://learn.chatgpt.com/docs/hooks)
