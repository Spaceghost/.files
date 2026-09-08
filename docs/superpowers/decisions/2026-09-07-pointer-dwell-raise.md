# Raise floating windows after pointer dwell

Keep focus following mouse entry immediately, then raise the same floating
window after one second over it. Moving inside the window does not restart the
timer. Leaving the target cancels it, including empty desktop space that keeps
the old keyboard focus. Newer focus, workspace and geometry changes, pointer
actions, destruction, fullscreen and locking also invalidate the pending raise.

Implement this in the pinned SwayFX compositor. Its normal IPC exposes neither
global cursor coordinates nor pointer leave events; a timer attached only to
window focus could raise a stale target. Reading raw input would not provide
the compositor's hit testing and would add unnecessary collection. The native
implementation uses existing pointer hit tests and one event-loop timer per
seat operation. At expiration it verifies the target, focus, workspace and
geometry again, then calls `container_raise_floating` without changing focus or
warping the pointer. Seat-operation and seat destruction remove timers/listeners.

Add `mouse_raise_delay` in milliseconds, from 0 through 60000, with zero as the
package default. A dedicated HOME include selects 1000 through a quiet runtime
IPC command. The include remains valid on stock Sway and on the old compositor
already running; the new behavior becomes available at the next graphical login
with the patched package. Preserve the current graphical session.

Use the repository's archived source, existing bottom-title patch and offline
signed-APK workflow. Retain exact new and previous package artifacts. Update
the installed package lock only after installation, since a candidate build
does not change the installed closure. Native verification uses a private
headless compositor, synthetic Foot clients and a virtual pointer. It checks
timing and cancellation and confirms that this SwayFX version's criteria
`focus` command raises an already focused floating view. No live input is read.
