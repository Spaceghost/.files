Paste into https://github.com/Alexays/Waybar/issues/new
Type: Bug. Labels: bug. Title below.

---

TITLE

On musl, SIGUSR2 reload can deadlock the whole bar: pthread_cancel of a module worker is inherited across fork() and fires while a FILE/mutex lock is held

---

WHAT HAPPENED

On Alpine Linux (musl 1.2.6, Waybar 0.15.0, GTK3), a bar with several `custom`
`exec` modules freezes completely after a burst of `SIGUSR2` reloads. The GUI
stops updating, the bar stops responding to clicks, and `ps` shows a growing
pile of extra `waybar` processes that never ran a script, plus zombies.

The cause is the interaction of three things that are individually fine on glibc:

1. A reload tears every module down. `~Custom` destroys its `SleeperThread`,
   whose destructor calls `stop()`, which calls `pthread_cancel()` on the worker.
2. `util::command::open()` and `forkExec()` `fork()` a `/bin/sh -c <cmd>` child
   from that same worker thread.
3. glibc turns a delivered cancellation into a forced stack unwind, so C++
   destructors run and locks are released. **musl unwinds nothing**: a cancelled
   thread is terminated where it stands, and anything it held stays held.

Two failure modes follow, both observed with gdb on the live process:

A. CANCELLATION INHERITED ACROSS fork(). If the worker has a cancellation
   pending (or receives it) between `fork()` and `execlp()`, the child — which
   has only that one thread — hits its first cancellation point, the
   `::close(fd[0])` just before `execlp`. The cancellation fires there;
   `pthread_exit()` on the last thread becomes `exit(0)`; `exit()` runs
   `__stdio_exit`, which tries to lock every `FILE`; and it blocks forever on a
   stream whose lock another parent thread held at the moment of `fork()`. The
   child never execs and never exits. This is the pile of stray `waybar`
   processes.

B. CANCELLATION WHILE A LOCK IS HELD. `command::read()` reads the child's
   output with `fgets()`, which holds the `FILE` lock across the read — a
   cancellation point. A worker cancelled there leaves that `FILE` locked
   forever, which is exactly the lock the children in (A) die on, and which
   would also hang Waybar's own `exit()`. The `Network` and `Battery` timer
   workers likewise call netlink/sysfs code under a `std::mutex`; a cancellation
   there leaves the mutex locked and the main thread blocks in `update()`.

Because a `FILE`/malloc lock ends up orphaned, the main thread then wedges on
its next allocation. gdb shows it in `gtk_container_remove -> ... -> g_malloc ->
__libc_malloc_impl` waiting on `__malloc_lock`, while several worker threads sit
in `__pthread_exit -> __pthread_tsd_run_dtors -> __libc_free` waiting on the
same lock. The bar is permanently deadlocked.

STEPS TO REPRODUCE

1. Alpine Linux edge, x86_64, musl. Waybar 0.15.0.
2. A config with a handful of `custom` modules that use `exec` on short
   intervals (any script that prints a line and exits, polled every few
   seconds, is enough).
3. Send `SIGUSR2` to the bar repeatedly in quick succession, e.g.
   `for i in $(seq 20); do pkill -USR2 -x waybar; sleep 0.3; done`, while the
   modules are mid-poll.

EXPECTED

Each reload rebuilds the modules and the bar keeps running.

ACTUAL

Within a few reloads the bar freezes. `ps -eLf | grep waybar` shows extra
`waybar` children that never exec'd a shell and a set of zombies; the main
thread is blocked in malloc under GTK teardown.

EVIDENCE

Child that never execs (gdb bt), musl 1.2.6 with debug symbols:

  #0 __futexwait
  #1 __lockfile
  #2 close_file            src/stdio/__stdio_exit.c:11
  #3 __stdio_exit          src/stdio/__stdio_exit.c:19
  #4 exit                  src/exit/exit.c:45          (code = 0)
  #5 __pthread_exit        src/thread/pthread_create.c:105
  #6 __cancel              src/thread/pthread_cancel.c:12
  #7 __syscall_cp_c        src/thread/pthread_cancel.c:33   (nr = 3, close)
  #8 close                 src/unistd/close.c:16
  #9..#11 waybar  (util::command::open, between fork and execlp)

Parent main thread, same freeze:

  #0 __futexwait  (__malloc_lock)
  ... __libc_malloc_impl -> g_malloc -> gtk_widget_unparent
      -> gtk_container_remove -> Gtk::Label::~Label  (module teardown)

Worker threads exiting, piled on the same lock:

  __pthread_exit -> __pthread_tsd_run_dtors -> __libc_free -> __malloc_lock

SUGGESTED FIX

Make the threaded fork/exec and the locked worker regions cancellation-safe,
which is correct on glibc too:

- Disable cancellation across `fork()`/`exec` in `util::command::open()` and
  `forkExec()` (a `CancellationGuard`, which Waybar already has, around the
  fork; the child inherits the disabled state). Use `_exit()` in the child if
  `exec` fails, never `exit()`.
- Read child output with `read(2)` on `fileno(fp)` instead of `fgets()`, so no
  `FILE` lock is held across the cancellation point.
- Wrap the `getline()` in `Custom::continuousWorker` and the mutex-holding
  regions of `Network`/`Battery` timer workers in a `CancellationGuard`. The
  threads still end promptly because `SleeperThread::stop()` clears `do_run_`;
  the remaining cancellation points (`epoll_wait`, `poll`, `recv`, `read`,
  `waitpid`) hold nothing.
- Stop `command::close()` spinning on `ECHILD` / retrying on `EINTR`.

A local build carrying this change (as `musl-cancellation-safety.patch`) has run
without the freeze. Happy to open a PR.

NOTES

Environment: MacBookPro11,5, Alpine edge x86_64, musl 1.2.6, GTK 3.24.52,
gtkmm 3.24.11, Waybar 0.15.0. A companion packaging bug on the same system —
gdk-pixbuf routing image decode through glycin, which forks the threaded bar and
adds a second source of these mid-reload forks — is tracked separately; it is
not the cause of this one, which reproduces with no image module at all.

---

SEPARATE (pre-existing) ISSUE seen alongside this: zombie children under reload storms

Under a rapid burst of reloads, `waybar` accumulates un-reaped zombie children
(seen on both 0.15.0-r4 and the patched r5; normal single reloads reap fine).
`util::command::open()` children are reaped inline by `command::close()` in the
worker, or by `~Custom` (`killpg`+`waitpid`); only `forkExec()` children go on
the global `reap` list. The `SIGCHLD` handler drains that list with

    for (auto it = reap.begin(); it != reap.end(); ++it)
      if (waitpid(*it, nullptr, WNOHANG) == *it) it = reap.erase(it);

which also mis-steps the iterator (after `erase`, `++it` skips an entry). A
global `waitpid(-1, …, WNOHANG)` reaper is not safe here because GLib's own
`GChildWatch` needs to reap the gspawn children it owns. A correct fix tracks
every forked pid (command::open and forkExec alike) in one list and reaps that
list with a `while (!list.empty() && (pid=waitpid(...))>0)` loop with correct
iterator handling. Filed for completeness; it is not the freeze.
