# Caps Lock Escape and notification indicator

Historical verification below describes the original count-based behavior.
The later [AI attention change](2026-09-07-ai-attention-led.md) replaces that
behavior with an off-by-default indicator that flashes while attributable AI
windows remain unvisited. Known windows clear individually on focus or close;
only an unresolved provider fallback can be acknowledged in the notification
center.

The user requested this after resuming the OpenSnitch package patch. The existing
Sway keyboard/session configuration is extended with `caps:escape`; Caps Lock
starts disabled. The original Escape key remains Escape.

`oldbook-notification-led` subscribes to SwayNC's count events. The indicator is
on whenever the notification center contains notifications, including retained
notifications and Do Not Disturb. It is off when the count reaches zero. Opening
the center does not acknowledge or delete notifications.

The helper runs as the desktop user, using the existing brightnessctl udev rule
and input-group membership. It discovers `*:capslock` LEDs dynamically, writes
zero once to detach the kernel trigger, then reconciles their actual brightness
once a second or on a notification event. No key-state changes or notification
body access are used. A runtime flock prevents duplicate helpers on reload.
An idle connection to the originating Wayland socket detects session exit and
compositor crashes; SIGTERM and normal shutdown also clear the LEDs. Subscriber
failures clear the state and retry with a two-second delay.

The session launcher closes its startup-lock descriptor in the helper, matching
the other background services. This prevents a helper from blocking later reloads.

## Evidence

- Five `unittest` cases pass: count transitions, unrelated LEDs, hotplug and
  external resets, malformed events, singleton/reconnect, compositor EOF with a
  stale socket path, and SIGTERM cleanup.
- Stock Sway validates the saved configuration; ShellCheck passes the launcher.
- Deployment to a disposable HOME succeeds twice; the second is idempotent.
- A Wayland keymap probe changed from `CAPS=Caps_Lock` to `CAPS=Escape` after the
  live input command. The probe discards keyboard events.
- Live SwayNC count was two. Both discovered Caps Lock LEDs read one; a synthetic
  notification was added and only that notification was closed. SIGTERM cleared
  both LEDs to zero; restarting the helper restored one. The original count of
  two was preserved, and a duplicate helper did not change the owning PID.

Local evidence and configuration backups are under
`~/.local/state/alpine-rice/caps-notifications/`. LED verification uses kernel
brightness readback; there is no physical photograph. A reboot and physical
keyboard unplug/replug were not performed; hotplug was exercised with disposable
sysfs-like fixtures. Rollback instructions are in `alpine/desktop/README.md`.

## References

- [Sway input configuration](https://github.com/swaywm/sway/blob/master/sway/sway-input.5.scd)
- [SwayNC 0.12.6 subscription interface](https://github.com/ErikReider/SwayNotificationCenter/blob/v0.12.6/src/client.vala)
- [Kernel LED brightness and trigger handling](https://github.com/torvalds/linux/blob/master/drivers/leds/led-class.c)
- [Input LED brightness readback](https://github.com/torvalds/linux/blob/master/drivers/input/input-leds.c)
