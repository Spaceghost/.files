# The cat parks the keyboard herself

Bed mode would only warm the machine while the session was already locked. The
reasoning was sound — an unlocked session means a person at the keyboard, and a
person is never warmed — but it was stated as a precondition the user had to
satisfy before the cat arrived. She does not check whether the session is locked
before she lies down, so in practice the feature was reachable only when Jack
happened to have locked before she settled, and the command deck's answer to
everything else was a refusal.

The rule is now stated as what it always meant: **the machine is warmed only
while its input is parked**, and there are two ways for that to be true. The
user locks the session, or the daemon engages the same guard Super+Shift+Escape
engages — `oldbook-watch`, a surface that takes the keyboard and pointer while
leaving the desktop visible and running. A decided judgement on an unlocked
session engages it, and it is released the moment she leaves. This supersedes
the earlier pin in `CAT-BED` that required a live lock record; the safety
reasoning behind that pin is preserved unchanged.

Three rules keep the guard honest, and each is a test.

A guard that will not start is a refusal to warm. Parking input is the
qualification, so failing to park means `present` stays false and no heat is
made, with the reason named in the published record.

A guard this daemon did not engage is never released. If the user parked their
own inputs, they leave watch mode when they say so and not when a cat wanders
off the keyboard.

The keyboard is handed back before anything else on the way out. In the
shutdown path the release sits above the lid inhibitor, the devices and the
parting record, because a daemon that dies still holding the user's input is
the one failure this feature must not have.

Engagement is driven by the *decided* judgement rather than by presence, so it
takes real evidence — no veto, five keys held together for two seconds, and a
corroborating signal — to take the keyboard. Release is driven by presence, so
the linger that stops the lid switch flapping also stops the guard flapping
while she shifts her weight. Heat still waits behind the twenty-second arming
countdown, which means the input is protected immediately and the machine warms
only after every precondition has held continuously; those two changes compose
rather than competing.

Reversal: drop `InputGuard` and restore `present = judgement['present'] and
locked and enabled` in `oldbook-cat`. Checks:
`alpine/tests/test_cat_guard.py`, and the existing detector, bed and fan suites
which continue to pass unchanged.
