# Native-quality still previews and Apple overview keys

The four-finger-down carousel uses high-quality still images. Each candidate
is captured once per opening; repainting, renaming or revisiting it does not
recapture it. Closing and reopening permits a fresh snapshot. Captures remain
asynchronous, so cancellation and modifier release never wait for image work.

Remove the 0.35 thumbnail scale from `grim -T`. Its toplevel path already uses
the full capture-buffer dimensions; an extra scale of two would only
interpolate those pixels. This SwayFX/wlroots scene-capture implementation
supplies a logical-pixel grid, which need not equal the original client's
Retina buffer. Keep every supplied pixel without claiming otherwise. Accept up to 16 Mi pixels,
enough for native internal-panel, 4K and 5K previews. Keep aspect ratios and use
GTK trilinear sampling for perspective/minified cards. Drop completed Future
RGB payloads once GTK owns the texture; a separate requested-identity set
preserves the still-image behavior and avoids retries within an opening.
Reuse cached static card nodes during movement, invalidating them when their
preview, content or theme changes. Navigation retains the elapsed-time
animation clock so repeated input does not restart its motion.

The MacBook's engraved F3/Mission Control and F4/Launchpad keys emit
XF86LaunchA and XF86LaunchB in the existing hid_apple auto mode. Bind those to
the window overview and the existing application launcher. The overview key
also closes its own view. Fn+F3/F4 continue to emit ordinary F3/F4 for apps;
do not intercept them or add global Ctrl+Up navigation.

Escape and the within-overview Mission Control binding close through
`mode default` alone. Launchpad leaves that mode and starts the menu. Do not
combine the mode change with an asynchronous cancel launcher: the controller
already closes on the mode event, and a delayed cancel can target the next
popup after an immediate reopen. A private native reproduction confirmed this
race by delaying only the old cancel launcher; three reopen cycles survive
with the mode-only bindings.

Determine an early modifier release only after actual keyboard entry. The
former map-time 50 ms guess committed a native held-Super gesture at 504 ms,
before its real release around 4.2 seconds. Wait for `GtkWindow.is_active`,
complete one Wayland synchronization, and defer once more so queued GDK focus
events can run. Recheck active state, focus epoch, popup identity and lifetime
before interpreting a zero modifier mask. Closing invalidates pending checks;
ordinary release events keep their existing behavior. Finish Wayland popup
destruction before sending a focus request over Sway's separate IPC socket.

Validate capture-buffer dimensions and card detail on a scale-two private output. Repaint a
synthetic window after capture and prove the current card stays unchanged,
then reopen and prove the new image appears. Preserve original navigation
evidence. Verify engraved-key behavior with synthetic native input and retain
the existing application function-key behavior. Activate only after the
focused checks and parser pass, preserving other sessions' ongoing changes.

The retained proof has distinct source scopes: the renderer before card
caching passed 18 native checks; the later cached quality/responsiveness run
passed seven quality/persistent groups before exposing premature modifier
commit. The corrected Escape bindings passed eight native checks, and Apple
keys passed eight real GUI checks, both before the keyboard-focus barrier.
That final barrier passes all 34 carousel unit tests. Its three native attempts
stopped during compositor or daemon startup before reaching a gesture, with
observed host load 49.05 on eight CPUs; all private processes were cleaned up.
Final native focus/release behavior and a full 18-check run remain pending.
Neither these results nor the earlier 19.115 ms median establish 60fps or a
physical presentation rate. Exact source hashes, failures and completed checks
are in `alpine/verification/carousel-quality/native-README.md` and
`focus-barrier-evidence.json`; activation is recorded separately.
