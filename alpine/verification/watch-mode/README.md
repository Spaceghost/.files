# Watch mode evidence

Watch mode is a **cat guard, not a lock**. `Super+Shift+Escape` parks keyboard
and pointer input off the desktop while the desktop stays fully visible and
fully running, so a long job can be watched — and sat on — without a key or a
paw reaching the session. `Super+Escape` remains the real lock and is untouched.

Recorded by `verify-headless` in a private headless SwayFX session (pixman,
1440×900) with the real `oldbook-watch`, the real `local.d/watch.conf` bindings
and a virtual keyboard on the seat; the live session was never locked and never
guarded. `evidence.json` records the binding state at each step and the guard's
readiness record.

| Capture | State |
| --- | --- |
| `desktop.png` | The private desktop before watch mode. |
| `watching.png` | Watch mode engaged: the painting and the terminal are unchanged and live, with the indicator card under the bar. |
| `indicator.png` | The card at native resolution. |
| `released.png` | After the release chord: the guard is gone and Sway is back in its default mode. |

What the run proved, in order:

| Step | Result |
| --- | --- |
| engaged | Sway's binding state became `watch`; the record carries `keyboard_proven: true`, meaning the compositor sent `wl_keyboard.enter` to the guard before anything claimed input was parked. |
| dirty hold | Super+Shift+Escape held 1.4 s **with a stray key also down** — a cat's hold — left watch mode engaged. |
| clean hold | Super+Shift+Escape held 1.4 s alone released it: exit 0, binding state `default`, readiness record removed. |
| killed | `SIGKILL` to the guard's process group put Sway back in `default` on its own, through the watchdog pipe. |

Two things this cannot prove, and they are the user's checks. A headless seat
has no keyboard until something makes one, so the run supplies a virtual
keyboard with `wtype`; a physical Apple keyboard and trackpad are not the same
device. And no cat was available.

```sh
alpine/verification/watch-mode/verify-headless --output /tmp/watch-preview
```
