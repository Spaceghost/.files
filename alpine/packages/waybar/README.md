# Waybar Sway IPC recovery package

This package preserves Alpine edge's Waybar 0.15.0 feature set and adds recovery
when Sway closes an event subscription. The stock module otherwise retains its
last workspace tree while its worker repeatedly reads the disconnected socket.

The patch is an adaptation of upstream commit `b0b46ec039199d99c36a0d6637e13e292d66fbdc`
for the 0.15.0 IPC implementation. It reconnects with bounded backoff, replays
both workspace subscriptions, and requests a fresh tree after reconnection.

Build in a disposable root with the pinned source archive:

```sh
alpine/packages/waybar/build-offline \
    --source ~/.local/state/oldbook/sources/Waybar-0.15.0.tar.gz \
    --work /tmp/oldbook-waybar-build
```

`rootbld` obtains build dependencies in its disposable APK root. It does not add
development packages to the live host. The build retains Alpine's main,
community, and explicitly tagged testing repositories over HTTPS. Review the
APK and native recovery evidence before replacing the installed `0.15.0-r3`.

## Reload safety on musl (r5)

`musl-cancellation-safety.patch` closes a freeze that took the whole bar down
within minutes of a burst of `SIGUSR2` reloads (`cue-sync` sends one per Fossil
commit). Waybar ends every module worker thread with `pthread_cancel()` when a
reload tears the modules down. glibc turns that into a forced unwind, so
destructors run; musl unwinds nothing, so whatever the thread held stays held.

Three consequences were caught with gdb on the live desktop (session
`01ECwveostDANdxWEWHA7psh`, 2026-09-13):

- A worker cancelled between `fork()` and `exec` in `util::command::open()`
  hands the pending cancellation to its child. The child's first cancellation
  point, `close()`, acts on it; `pthread_exit()` on the child's only thread
  becomes `exit(0)`; `__stdio_exit` then blocks forever on a `FILE` lock some
  other thread of the parent held at fork time. The child never execs and
  never exits (`ps` shows extra `waybar` processes that never ran a script).
- A worker cancelled inside `fgets()`/`getline()` leaves that `FILE` locked
  forever, which is the lock those children die on, and which would also hang
  Waybar's own `exit()`.
- A worker cancelled inside a netlink or sysfs read under a module mutex leaves
  the mutex locked; the main thread then blocks in `update()`.

The patch disables cancellation across `fork()`/`exec` (the child inherits the
disabled state and uses `_exit(127)` instead of `exit(0)` if `exec` fails),
reads command output with `read(2)` instead of `fgets()`, guards `getline()`
in the continuous custom worker and the locked regions of the network and
battery workers with the `CancellationGuard` Waybar already uses around its
condition-variable waits, and stops `util::command::close()` spinning on
`ECHILD`. The threads still end promptly: `stop()` clears `do_run_`, and the
remaining cancellation points (`epoll_wait`, `poll`, `recv`, `read`, `waitpid`)
hold nothing.

This belongs upstream; the report is in `docs/upstream/waybar-musl-reload-freeze.md`.
