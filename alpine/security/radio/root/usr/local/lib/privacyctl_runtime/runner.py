"""OpenRC entrypoint with reciprocal guardian/owner process lifetimes."""
import ctypes
import fcntl
import os
from pathlib import Path
import select
import signal
import stat
import time

from .adapter import NativeAdapter, RUNTIME
from .dhcp import DHCPManager, _private_directory
from .ipc import Server
from .service import Owner


def guarded(child_main, block, runtime=RUNTIME):
    """Block before launch, on owner death, and before requested shutdown.

    The private guard lock remains held in both processes until the owner is
    gone. A killed guardian asks its child to shut down through PDEATHSIGTERM;
    a killed owner is observed by its guardian through a pidfd. No PID record
    from a previous invocation is trusted or signalled.
    """
    directory = _private_directory(Path(runtime))
    lock = child_fd = None
    child_pid = None
    stopping = [False]
    handlers = {}
    def stop(_signum, _frame):
        stopping[0] = True
    try:
        lock = os.open('guardian.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW |
                       os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=directory)
        info = os.fstat(lock)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise RuntimeError('unsafe radio guardian lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # An inherited SIG_IGN would auto-reap an early-exiting owner and break
        # the reserved-child-PID guarantee before pidfd_open captures it.
        handlers[signal.SIGCHLD] = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        for sig in (signal.SIGTERM, signal.SIGINT):
            handlers[sig] = signal.signal(sig, stop)
        block()
        if stopping[0]:
            return 0
        parent = os.getpid()
        child_pid = os.fork()
        if child_pid == 0:
            code = 1
            try:
                libc = ctypes.CDLL(None, use_errno=True)
                if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), 'owner parent-death setup failed')
                if os.getppid() != parent:
                    stopping[0] = True
                if not stopping[0]:
                    child_main(lambda: stopping[0])
                code = 0
            except BaseException:
                code = 1
            finally:
                try:
                    block()
                except BaseException:
                    code = 1
                os._exit(code)
        try:
            child_fd = os.pidfd_open(child_pid)
            stop_sent = False
            deadline = None
            while True:
                if stopping[0] and not stop_sent:
                    try:
                        block()
                    finally:
                        signal.pidfd_send_signal(child_fd, signal.SIGTERM)
                    stop_sent = True
                    deadline = time.monotonic() + 12
                if select.select([child_fd], [], [], .025)[0]:
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                    if not select.select([child_fd], [], [], 3)[0]:
                        raise RuntimeError('radio owner did not terminate')
                    break
            # Block before reaping or returning ownership to a replacement.
            block()
            _, status = os.waitpid(child_pid, 0)
            child_pid = None
            return os.waitstatus_to_exitcode(status)
        finally:
            if child_pid is not None:
                try:
                    block()
                finally:
                    if child_fd is not None:
                        try:
                            signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        # A still-unreaped direct child reserves this numeric PID.
                        os.kill(child_pid, signal.SIGKILL)
                    os.waitpid(child_pid, 0)
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        for descriptor in (child_fd, lock, directory):
            if descriptor is not None:
                os.close(descriptor)


def run(legacy):
    """Fixed production dependencies; CLI callers cannot redirect native paths."""
    adapter = NativeAdapter(legacy)
    def child(stop_requested):
        server = Server()
        server.open()
        original_check = adapter.check_generation
        def check_generation(generation):
            if stop_requested():
                adapter.block_all()
                raise RuntimeError('radio owner is stopping')
            original_check(generation)
        adapter.check_generation = check_generation
        owner = Owner(server=server, adapter=adapter, dhcp=DHCPManager(RUNTIME),
                      applier_factory=adapter.applier)
        try:
            owner.start()
            while not stop_requested():
                owner.step()
                time.sleep(.025)
        finally:
            try:
                owner.shutdown()
            finally:
                server.close()
    result = guarded(child, adapter.emergency_off)
    if result:
        raise RuntimeError('radio owner exited unexpectedly; radios blocked')
