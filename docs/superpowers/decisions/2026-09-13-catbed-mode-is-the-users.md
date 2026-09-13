# Catbed mode is the user's alone

The 2026-09-09 decision, "The cat parks the keyboard herself", had the cat
watcher engage the Super+Shift+Escape guard on a decided judgement so that bed
mode could warm an unlocked machine, and release it when the watcher stopped.
Jack has since drawn the line the other way, in three sentences: "The only way
I should be able to unlock it is super+shift+esc, and there should be no
automatic removal of catbed mode when the cat gets up. It is manually applied
and manually unapplied. It works through all things all locks and all."

So catbed mode is applied by hand and ended by hand, and nothing on the machine
does either for him. Taking that literally changed three things.

**The watcher no longer touches the guard.** It reads the guard's own record,
exactly as it reads the locker's, and treats either as parked input; a decided
cat on a live desktop is simply not warmed. `InputGuard` is gone from
`oldbook-cat`, and so is the release in its shutdown path — there is nothing
of the user's to hand back.

**The guard outlasts everything but the held chord.** Losing the keyboard used
to end it, on the argument that a guard not holding the keyboard is not doing
what it says. But the screen lock takes the keyboard from every layer surface
and returns it at the password, so that rule ended catbed mode at every idle
lock — the opposite of "works through all locks". It now waits, holding the
pointer and the empty mode, and records that the keyboard is elsewhere. A Sway
reload resets the binding mode, so the guard subscribes to mode events and
re-enters `watch`. And while it is up it holds what the lock holds — the
power, suspend and hibernate keys, and SysRq — because a cat on an unlocked
desktop reaches those keys too.

**The emergency chord is gone.** `Ctrl+Alt+Shift+Super+w` was bound inside the
mode as the exit for a wedged guard, deliberately awkward for a paw. But the
detector's own definition of a cat is five keys held at once, and any chord
Sway answers is a chord she can produce. Recovery is `oldbook-watch stop` from
a terminal or over SSH, or killing the guard, whose watchdog pipe restores the
mode.

Reversal: restore `InputGuard` and the engage-on-decided-judgement line in
`oldbook-cat`, `on_keyboard_lost=lambda: finish('keyboard-lost')` in
`oldbook-watch`, and the binding in `watch.conf`. The superseded checks are the
2026-09-09 revisions of `alpine/tests/test_cat_guard.py` and
`alpine/tests/test_watch_mode.py`.
