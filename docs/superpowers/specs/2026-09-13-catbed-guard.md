# What is held while input is parked

**The ask.** "When I lock the computer, I want the power button completely
disabled so my cat can sit on the keyboard and never shut down or bother the
machine … Make sure there's no amount of pressing or holding of any keys that
will shut down the machine except magically my password." The lock already
held a `handle-power-key` inhibitor (2026-09-08). This closes what it did not,
from the list he chose: the suspend and hibernate keys, Magic SysRq while
locked, and the acpid landmine. He declined the `Ctrl+Alt+Del` change on the
rescue ttys, so `/etc/inittab` is untouched.

**One policy, two parkers.** The lock and catbed mode both park input and both
hold the same things, so the policy lives in one module, `catbed_guard.py`,
and one file, `~/.config/oldbook/catbed.json`:

```json
{"version": 1, "keys": ["power", "suspend", "hibernate"],
 "sysrq": {"guard": true, "mask": 382}}
```

`keys` may add `lid`; an empty list holds no key. `mask` is what `kernel.sysrq`
is narrowed to while parked. 382 is every SysRq function except reboot and
power-off, chosen over 0 so that `Alt+SysRq+S` and `+U` can still sync and
remount a wedged machine before the SMC's hardware cut; the internal Apple
keyboard has no physical SysRq key, so the path is reachable only from an
external keyboard, and 0 is a one-line change for anyone who wants it. Every
value is checked and a bad one falls back to its default alone.

**Holds are pipes.** Each hold is a process that waits on a pipe: the login
manager's inhibitor (`elogind-inhibit … -- cat`) and the SysRq helper both. The
write end is handed to the parker's process tree — the locker, or the guard —
so release is the pipe closing, however that tree ends. Nothing has to remember
to release anything.

**The SysRq helper is root's.** `/proc/sys/kernel/sysrq` is root-writable only,
so `catbed-sysrq-hold` is installed root-owned under `/usr/local/sbin` and run
through doas, in the shape of `oldbook-fan-hold`: it refuses to run unless
root-owned and unwritable, imports nothing from HOME, forks a restorer in its
own session before writing so a `kill -9` still restores, and keeps a ledger
under `/run/catbed-sysrq/` so nested holds (the idle lock arriving while catbed
mode is up) restore the kernel's own value only when the last holder leaves and
never loosen an earlier holder's mask (the effective mask is the AND of every
live holder's). It prints `holding` once the mask is written, and the client
does not count a hold it has not heard that word for, because doas will
happily start a helper that then refuses.

**Failures are said in the helper's words.** A hold that is wanted and cannot
be taken is announced at critical urgency with the helper's own stderr in the
body, and the lock or guard proceeds without it. A host with no helper
installed at all — the Bazzite replay — is logged to stderr and not announced.

**Verification.** Policy, holds and the helper are exercised against a
synthetic sysrq file and ledger in `alpine/tests/test_catbed_guard.py`,
including the crash case where the ledger outlives its holders; the lock and
guard tests pin that both take the holds and let go last. Not done, by the
standing rule that agents do not exercise live desktop features: no live lock
or catbed mode was taken from this session. The live checks are
`doas catbed-sysrq-hold status` while locked, `oldbook-watch status` in catbed
mode, and elogind logging "Power key pressed short." and nothing more.
