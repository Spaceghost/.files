# Desktop scheduling verification

`oldbook-ui-priority` is a one-shot helper installed by
`alpine/bin/install-desktop-system` as root-owned mode 0755 at
`/usr/local/sbin/oldbook-ui-priority`. Session/daemon startup calls it through
the existing `doas` authorization. It does not add a privilege rule or a
scheduler daemon. Scans require `--session "$SWAYSOCK"`; optional positive PID
arguments narrow the scan or target a daemon itself without scanning. `--check`
only reports safe process names, thread IDs and scheduling attributes. The
session socket must belong to the caller. Its peer credentials identify the
compositor; other targets require that exact SWAYSOCK environment entry, so
private preview sessions cannot boost the live session.

The helper validates the caller through `DOAS_USER`, exact native executable
paths and root ownership, or the known caller-owned Python daemon paths. It
recognizes the optional `-S` interpreter startup flag. The still-running,
replaced SwayFX executable is validated through its open `/proc/PID/exe` inode.
System Python running the versioned Superhold daemon is also recognized.
Unrelated commands, terminals, shells and background generation are excluded.

Normal Sway/SwayFX threads receive nice -10 and other approved UI threads nice
-5. Non-normal policies are preserved, including realtime and deliberately
batched workers. Reset-on-fork is armed before any negative nice value, so new
child applications and capture processes start at nice 0. This also means new
threads created after the one-shot scan can start at normal priority; the main
UI thread and existing renderer threads are prioritized at startup.
Each daemon request reaps its owned helper in a short-lived background thread;
the UI does not wait for the helper to exit, and successful requests do not
leave zombie children. This does not rescan workers created later or change
the one-shot priority limitation.

Alpine's musl scheduler wrappers return ENOSYS. The helper first uses Python's
OS interface, then falls back to the Linux x86_64 scheduler syscalls confirmed
in the installed `asm/unistd_64.h`. It fails safely on an unsupported fallback
ABI. This follows the approach documented in
[util-linux chrt](https://github.com/util-linux/util-linux/blob/master/schedutils/chrt.c).
The [Linux scheduler manual](https://man7.org/linux/man-pages/man7/sched.7.html)
documents negative-nice reset for children.

`private-child-reset.json` records a private short-lived verifier moving itself
from nice 0 to -5 with reset enabled. Both its forked child and newly executed
Python child were observed at nice 0 and SCHED_OTHER. No desktop process was
changed by this verification. `before.json` is a read-only snapshot of the
approved live processes before installation or activation.

Validation commands:

```sh
python3 -B -m unittest discover -s alpine/tests -p test_ui_priority.py -v
doas -n /usr/bin/python3 -I alpine/tests/verify_ui_priority.py
doas -n /usr/bin/python3 -I alpine/bin/oldbook-ui-priority --check --session "$SWAYSOCK"
```

To revert the policy, remove its session startup hook and restore the helper
from the installer's backup if necessary. A new login then starts normally.
For an immediate reversal without logging out, use the recorded selected thread
IDs to restore their prior nice values; do not indiscriminately renice all user
processes. Reset-on-fork may remain enabled until those daemons restart.
