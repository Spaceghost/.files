# Caps Lock AI attention tracking

Caps Lock continues to send Escape. Its light is off when no attributable AI
window needs a visit and alternates every half second while one or more windows
remain pending. The phase starts when the pending set changes from empty to
nonempty. Later alerts add targets without resetting that phase.

`mbp-intel-ai-notification-stream` passively observes freedesktop `Notify` method
calls and emits only `attention` plus the attributed provider: `codex`, `claude`,
or `chatgpt`. It does not log or forward notification summaries, bodies, actions,
icons, or conversation text. Native attribution uses the notification's exact
application name or desktop-entry hint. Browser attribution additionally
requires an exact browser identity and a validated `x-kde-origin-name` hint for
`chatgpt.com`, `chat.openai.com`, or `claude.ai`. These fields are application
claims used for an indicator, not cryptographic sender identities.

The current SwayNC build does not advertise the Chromium origin capability, and
generic Firefox and Chromium notices observed locally carry no usable origin
hint. They are deliberately ignored. Browser ChatGPT or Claude can participate
only when the browser actually emits a desktop notice with the validated origin
hint. A page title or an open browser window never creates attention by itself.

## Pending windows and acknowledgement

On each attributed notice, `mbp-intel-notification-led` takes a Sway tree snapshot
and resolves provider windows through the shared application resolver. A fresh,
owned Codex runtime event record can select one exact window by terminal device
or tmux pane. Otherwise, one candidate becomes the exact target; with multiple
candidates, every currently unfocused candidate is conservatively added. A
candidate already focused when the notice arrives counts as visited.

Sway `window::focus`, `window::close`, and `window::new` events refresh this set.
Focusing one exact target clears only that container. Closing it also clears it.
Other pending containers continue the flash. Terminal title, move, floating and
geometry events do not trigger process or tmux scans and cannot acknowledge an
alert.

When a notice has no attributable window, the helper stores a provider-level
fallback. It converts that fallback to exact candidates if windows later appear.
Focusing a matching provider window acknowledges it; opening SwayNC's control
center acknowledges only unresolved fallbacks. Opening the center never clears
known exact targets. This gives an unknowable browser or native notice a human
acknowledgement path without applying arbitrary expiry to known windows.

The pending set is runtime-only and contains provider names and Sway container
numbers. It is neither logged nor persisted. A notification-subscriber failure
clears the set, turns the LEDs off, and retries after two seconds. Compositor
exit, SIGINT, SIGTERM and normal shutdown also turn the LEDs off. A runtime flock
prevents duplicate services. Hotplugged Caps Lock LEDs are discovered and their
actual brightness is reconciled throughout both flash phases and idle state.
The helper never synthesizes a Caps Lock key event.

## Provider signals

Codex uses its supported completion callback and notification-only
`PermissionRequest` hook. Its existing callback and hook definitions remain
unchanged. Claude Code uses supported `PermissionRequest`, selected
`Notification`, and main-agent `Stop` hooks through its selective settings
installer. Both helpers call `notify-send` with content-free provider titles.
ChatGPT and browser Claude require a native desktop notification that the stream
can attribute; no completion state is inferred from browser UI.

## Verification

Focused tests cover source filtering on an isolated D-Bus session, intact
notification delivery, continuous phase timing, no phase reset, exact per-window
focus and close acknowledgement, multi-window retention, notification-center
fallback acknowledgement, Codex route validation, malformed input, hotplug,
singleton startup, subscriber restart, compositor EOF and signal cleanup.
Application resolver tests cover native Ghostty's
`com.mitchellh.ghostty` app ID with foreground Codex and Claude processes.

Runtime evidence is in `alpine/verification/ai-attention-led.json`. The previous
finite-burst artifact was superseded and must not be used to describe the current
pending-window behavior.

## Recovery

To disable the indicator while preserving Caps-as-Escape, remove only the
`mbp-intel-notification-led` startup block from `mbp-intel-session`, then terminate
the PID recorded in `$XDG_RUNTIME_DIR/mbp-intel-notification-led.lock`. Shutdown
clears the light. Restore the startup block or run the helper from the Wayland
session to re-enable it.
