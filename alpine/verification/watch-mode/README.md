# Catbed mode evidence

Catbed mode is a **cat guard, not a lock**. `Super+Shift+Escape` parks keyboard
and pointer input off the desktop while the desktop stays fully visible and
fully running, so a long job can be watched — and sat on — without a key or a
paw reaching the session. `Super+Escape` remains the real lock and is untouched,
and leaving is the user's alone: the same chord held for a second with no other
key down.

Recorded on 2026-09-13 by `verify-headless` in a private headless SwayFX
session (pixman, 1440×900) with the real `oldbook-watch`, the real
`local.d/watch.conf` and a virtual keyboard on the seat. The harness seals the
guard off from the live session — no notification on its bus, no cue through
its speakers, and a policy that holds no key and leaves SysRq alone, so no
elogind inhibitor or doas hold is taken on the machine running it — which is
why the record shows `holds: 0`. The live session was never locked and never
guarded. `evidence.json` records the binding state at each step and the
guard's readiness record.

| Capture | State |
| --- | --- |
| `desktop.png` | The private desktop before catbed mode. |
| `watching.png` | Catbed mode engaged: the painting and the terminal are unchanged and live, with the card under the bar. |
| `indicator.png` | The top band at native resolution, where the card sits. |
| `released.png` | After the release hold: the guard is gone and Sway is back in its default mode. |

What the run proved, in order:

| Step | Result |
| --- | --- |
| engaged | Sway's binding state became `watch`; the record carries `keyboard_proven: true`, meaning the compositor sent `wl_keyboard.enter` to the guard before anything claimed input was parked. |
| dirty hold | Super+Shift+Escape held 1.4 s **with a stray key also down** — a cat's hold — left catbed mode engaged. |
| reload | `swaymsg reload` reset the binding mode to default and, as Sway does, sent no mode event; the guard heard the reload as a workspace event, re-entered `watch`, recorded `reentries: 1`, and was still alive. |
| clean hold | Super+Shift+Escape held 1.4 s alone released it: exit 0, binding state `default`, readiness record removed. |
| killed | `SIGKILL` to the guard's process group put Sway back in `default` on its own, through the watchdog pipe. |

This run is the one that first passed after two defects were found the same
day. The 2026-09-13 rewrite had left the `watch` mode's block empty, and Sway
creates a mode only from a line inside its block, so the mode did not exist
and the guard refused to start ("Sway would not enter the watch mode"); and
the guard listened for mode events to re-enter after a reload, which Sway
never sends for one. The block now carries a `set` line, and the subscription
covers the workspace event a reload does send.

Three things this cannot prove, and they are the user's checks. A headless
seat has no keyboard until something makes one, so the run supplies a virtual
keyboard with `wtype`; a physical Apple keyboard and trackpad are not the same
device. The screen lock is not driven here: that on unlock the compositor
hands the keyboard back to the seat's exclusive overlay surface is read from
sway's own source (`handle_unlock` re-focuses through `seat_set_focus`, which
re-applies the exclusive layer), not seen. And no cat was available.

```sh
alpine/verification/watch-mode/verify-headless --output /tmp/watch-preview
```
