# Lock screen evidence

Rendered by `render-headless` in a private headless SwayFX session (pixman
renderer, 2880×1800 at scale 2) with the real `oldbook-lock` helper and the
installed `swaylock-effects`; the live session was not locked. `evidence.json`
records the compositor and locker hashes, the painting hash, readiness
timings for a cold and a warm scene cache, the readiness record naming the
locker, and the exact arguments used.

| Capture | State |
| --- | --- |
| `idle.png` | Blurred, darkened painting; clock and date; caption card; ring invisible. |
| `typing.png` | Amber ring and key highlight after typing into the locker. |
| `cleared.png` | Border ring and “Cleared” after Escape. |
| `capslock.png` | Ring state while typing with a virtual Caps Lock; the Caps Lock text did not appear because the virtual keyboard's lock state did not reach the locker. |
| `relocked.png` | A second private session locked from the warm cache, after the dissolve. |

Captures are the full-resolution screenshots scaled to 1440×900. The desktop
before locking and the backspace state are captured by the script but not
stored here. Timings in `evidence.json` were taken under heavy build load;
the quiet-run numbers are recorded beside them.

```sh
alpine/verification/lock-screen/render-headless --output /tmp/lock-preview
```
