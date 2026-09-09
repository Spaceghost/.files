"""Bed mode: make the laptop a warm place to lie on, and never a hot one.

The cat sits on a locked machine and the machine is cold. Bed mode answers by
running warm on purpose. Two rules shape everything below.

The first is that heat should be a by-product, not the product. A registry of
real jobs is consulted first -- each job is a probe that says whether there is
genuinely anything to do and a command that does it -- and only when nothing
answers does the plain controlled load run. The shipped registry is empty, and
deliberately so: this machine's standing rule is that compilation happens on
the Alienware, so the obvious "worthwhile compiling" job is exactly the one
that is not allowed here. The mechanism is built and tested; the entry is the
user's to add.

The second is that this is a feature which deliberately makes a laptop hot and
deliberately holds its fans down, so every part of it is built to fail cold:

  * The load is a proportional controller aiming at a target well under the
    ceiling, not a flat-out burn. It backs off long before anything trips.
  * Ceilings come from `thermal`, which reads three sensor families and calls
    an unreadable sensor a stop rather than a zero.
  * A shut lid switches the whole table to stricter numbers, and an unknown lid
    is treated as shut.
  * Fans are held only through the privileged helper, whose hold survives
    exactly as long as the pipe from this process, and which lets go at its own
    release line without asking. A released hold is never re-taken in a sitting.
  * Mains only. Warming a laptop off the battery for a cat is a flat battery.
  * The workers are children with PR_SET_PDEATHSIG, so a kill -9 here takes the
    heat with it. Load and heater share a fate on purpose: the worst case this
    design permits is fans stuck low on a machine with nothing running.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thermal  # noqa: E402

HELPER = '/usr/local/sbin/oldbook-fan-hold'
DOAS = 'doas'
# The helper releases on its own if this many seconds pass without a renewal;
# the daemon renews every tick, so the margin is several missed ticks wide.
HOLD_DEADLINE = 10.0
# A hold that refuses to start this many times is given up on for the sitting.
FAN_HOLD_ATTEMPTS = 3
# A sitting cannot outlast this, however comfortable she is.
MAX_SITTING = 3 * 3600.0
# Workers are half the hardware threads: the same watts spread over more cores
# runs cooler per core, which is what keeps the fans down.
WORKERS = max(1, (os.cpu_count() or 2) // 2)
# One tenth of a second of work-then-sleep. Short enough that the duty cycle is
# smooth, long enough that the scheduling overhead is not the load.
SLICE = 0.1

# The load itself. Deliberately tiny and deliberately not a shell: it reads a
# duty fraction from its stdin and exits the moment that pipe closes, so it can
# never outlive the daemon even if the daemon is killed uncatchably.
WORKER = '''
import os, select, sys, time
os.nice(19)
duty, slice_ = 0.0, float(sys.argv[1])
while True:
    if select.select([0], [], [], 0)[0]:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            duty = max(0.0, min(1.0, float(line.strip())))
        except ValueError:
            pass
    if duty <= 0.0:
        time.sleep(slice_)
        continue
    end, value = time.monotonic() + slice_ * duty, 0
    while time.monotonic() < end:
        for _ in range(4000):
            value = (value * 1103515245 + 12345) & 0xffffffff
    rest = slice_ * (1.0 - duty)
    if rest > 0:
        time.sleep(rest)
'''


def die_with_parent():
    """Ask the kernel to kill this child when its parent goes.

    The pipe already covers the ordinary cases; this covers the case where the
    child is wedged and not reading it. Best effort, and never fatal.
    """
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0)
    except Exception:                                  # noqa: BLE001 - never fatal
        pass


def helper_path():
    return os.environ.get('OLDBOOK_FAN_HELPER') or HELPER


def helper_command(action, **options):
    """How to invoke the fan helper: through doas, unless a test aims elsewhere.

    A root process must not be a file the user can rewrite, so the installed
    helper is checked for root ownership and for not being group or world
    writable before it is ever run. A helper pointed at a synthetic tree by
    OLDBOOK_FAN_HELPER is the test's own copy and runs unprivileged.
    """
    path = Path(helper_path())
    arguments = [action]
    for name, value in sorted(options.items()):
        if value is not None:
            arguments += ['--' + name.replace('_', '-'), str(value)]
    if os.environ.get('OLDBOOK_FAN_HELPER'):
        return [sys.executable, str(path), *arguments]
    try:
        info = path.stat()
    except OSError:
        return None
    if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return None
    if not shutil.which(DOAS):
        return None
    return [DOAS, '-n', str(path), *arguments]


class FanHold:
    """The client side of the guaranteed release: one pipe, held open."""

    def __init__(self, root=None, hwmon=None):
        self.root = root
        self.hwmon = hwmon
        self.process = None
        self.released = False
        self.reason = None
        self.refusals = 0

    @property
    def active(self):
        return self.process is not None and self.process.poll() is None

    def start(self, regime):
        """Take the hold. A refusal is reported, never raised: the fans running
        normally is a perfectly good outcome for a cat, and never a reason to
        abandon the rest of bed mode."""
        if self.active or self.released:
            return self.active
        command = helper_command('hold', regime=regime, deadline=HOLD_DEADLINE,
                                 root=self.root, hwmon=self.hwmon)
        if command is None:
            return self.refuse('no trusted fan helper is installed')
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True)
        except OSError as error:
            self.process = None
            return self.refuse(f'the fan helper did not start ({error})')
        return True

    def refuse(self, reason):
        """A hold that will not start is given up on rather than retried forever.

        Otherwise a missing or forbidden helper would mean spawning a doas
        every tick for as long as the cat sits there, which is a lot of noise
        for a machine whose fans are simply going to run normally.
        """
        self.reason = reason
        self.refusals += 1
        if self.refusals >= FAN_HOLD_ATTEMPTS:
            self.released = True
        return False

    def renew(self, regime):
        """Say we are still here. A helper that has gone is not restarted."""
        if not self.active:
            if self.process is not None:
                self.stop('the fan helper exited on its own')
            return False
        try:
            self.process.stdin.write(f'renew {regime}\n'.encode())
            self.process.stdin.flush()
        except (OSError, ValueError):
            self.stop('the fan helper stopped listening')
            return False
        return True

    def stop(self, reason='asked to stop'):
        """Release, and mark the hold spent for the rest of the sitting."""
        self.released = True
        self.reason = reason
        process = self.process
        self.process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                try:
                    process.stdin.write(b'release\n')
                    process.stdin.flush()
                except (OSError, ValueError):
                    pass
                process.stdin.close()
            process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass


def available_work(jobs, environment=None):
    """The first registered job whose probe says there is real work waiting.

    A job without a probe is never chosen: "is there anything to do" has to be
    answered by something that can say no, or the load stops being useful work
    and becomes a command that happens to run whenever a cat sits down.
    """
    for job in jobs or ():
        probe, run = job.get('probe'), job.get('run')
        if not (isinstance(probe, list) and probe and isinstance(run, list) and run):
            continue
        try:
            found = subprocess.run(probe, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=environment, timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        if found.returncode == 0:
            return job
    return None


class BedMode:
    """One sitting's worth of deliberate warmth, and every way it can end."""

    def __init__(self, jobs=None, smc_root=None, hwmon_root=None, clock=time.monotonic):
        self.jobs = list(jobs or ())
        self.smc_root = smc_root
        self.hwmon_root = hwmon_root
        self.clock = clock
        self.workers = []
        self.job = None
        self.job_process = None
        self.fans = FanHold(smc_root, hwmon_root)
        self.running = False
        self.coasting = False
        self.duty = 0.0
        self.started_at = None
        self.stopped_reason = None
        self.safety_stop = False
        self.notes = []

    # ---- the load ----------------------------------------------------------

    def spawn_workers(self, count=WORKERS):
        for _ in range(count):
            try:
                self.workers.append(subprocess.Popen(
                    [sys.executable, '-c', WORKER, str(SLICE)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, preexec_fn=die_with_parent, close_fds=True))
            except OSError:
                break
        return len(self.workers)

    def spawn_job(self, job, environment=None):
        try:
            self.job_process = subprocess.Popen(
                job['run'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, preexec_fn=die_with_parent,
                env=environment, close_fds=True)
            self.job = job.get('id', 'work')
        except (OSError, KeyError):
            self.job, self.job_process = None, None
        return self.job

    def push(self, duty):
        """Tell every worker how hard to push; a dead worker is dropped."""
        self.duty = duty
        alive = []
        for worker in self.workers:
            if worker.poll() is not None:
                continue
            try:
                worker.stdin.write(f'{duty:.3f}\n'.encode())
                worker.stdin.flush()
                alive.append(worker)
            except (OSError, ValueError):
                continue
        self.workers = alive
        return len(alive)

    def kill_load(self):
        for worker in self.workers:
            try:
                if worker.stdin is not None:
                    worker.stdin.close()
                worker.terminate()
            except (OSError, ValueError):
                pass
        for worker in self.workers:
            try:
                worker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    worker.kill()
                except OSError:
                    pass
        self.workers = []
        if self.job_process is not None:
            try:
                self.job_process.terminate()
                self.job_process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self.job_process.kill()
                except OSError:
                    pass
        self.job_process, self.job = None, None
        self.duty = 0.0

    # ---- the sitting -------------------------------------------------------

    def start(self, environment=None):
        """Begin warming: real work if there is any, the plain load otherwise."""
        if self.running:
            return True
        self.stopped_reason = None
        self.notes = []
        job = available_work(self.jobs, environment)
        if job is not None and self.spawn_job(job, environment):
            self.notes.append(f'running real work: {self.job}')
        else:
            self.notes.append('no real work was waiting; a plain controlled load')
        self.spawn_workers()
        self.running = bool(self.workers) or self.job_process is not None
        self.coasting = False
        self.started_at = self.clock()
        if not self.running:
            self.stopped_reason = 'nothing could be started'
        return self.running

    def stop(self, reason, safety=False):
        """End the sitting. Fans first, then the heat, then the bookkeeping.

        Fans before load is the safe order: releasing the hold costs nothing if
        the machine is already cool and buys cooling immediately if it is not,
        whereas cutting the load first would leave a hot machine on a held fan
        for as long as the tear-down takes. `safety` marks the stops the caller
        must not simply try again -- a ceiling reached, a sensor gone silent.
        """
        self.fans.stop(reason)
        self.kill_load()
        self.running = False
        self.coasting = False
        self.safety_stop = self.safety_stop or safety
        if self.stopped_reason is None:
            self.stopped_reason = reason

    # ---- one tick ----------------------------------------------------------

    def update(self, values, lid_shut):
        """Read the ceilings and act. Called on a fixed tick, not on events."""
        limits = thermal.regime(lid_shut)
        name = 'closed' if lid_shut else 'open'
        if not self.running:
            return self.report(values, limits, name)
        if self.started_at is not None and self.clock() - self.started_at > MAX_SITTING:
            self.stop('the sitting reached its maximum length')
            return self.report(values, limits, name)
        state, reasons = thermal.verdict(values, limits, self.coasting)
        if state == 'stop':
            self.stop('; '.join(reasons), safety=True)
            return self.report(values, limits, name)
        # Fans before load, always: the hold is given up at a lower temperature
        # than the one that pauses the heating, so the machine gets its cooling
        # back before it ever needs the load to stop.
        if not self.fans.released:
            action, why = thermal.fan_verdict(values, limits, self.fans.active)
            if action == 'release':
                self.fans.stop('; '.join(why) or 'the fans are needed')
            elif action == 'hold' and not self.fans.active:
                self.fans.start(name)
        if self.fans.active:
            self.fans.renew(name)
        self.coasting = state == 'coast'
        self.push(0.0 if self.coasting else thermal.duty(values, limits, self.duty))
        return self.report(values, limits, name)

    def report(self, values, limits, name):
        return {'running': self.running, 'coasting': self.coasting,
                'duty': round(self.duty, 3), 'workers': len(self.workers),
                'work': self.job, 'regime': name,
                'fans_held': self.fans.active, 'fans_note': self.fans.reason,
                'ceiling': limits['cpu_ceiling'], 'target': limits['cpu_target'],
                'temperatures': {name: (None if value is None else round(value, 1))
                                 for name, value in values.items()},
                'stopped_reason': self.stopped_reason, 'safety_stop': self.safety_stop,
                'notes': list(self.notes)}


def restore_fans(root=None):
    """Put every fan back on automatic, with nothing to consult but the hardware.

    Run at session start and by `oldbook-cat fans restore`. It is the answer to
    the only failure the pipe cannot cover -- both the holder and its restorer
    killed in the same instant -- and it costs one write per fan.
    """
    command = helper_command('restore', root=root)
    if command is None:
        return None
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or done.stderr.strip()


def load_jobs(document):
    """The work registry out of the interaction config, defensively."""
    jobs = document.get('work')
    return [job for job in jobs if isinstance(job, dict)] if isinstance(jobs, list) else []


def describe(values=None, lid_shut=None):
    """A snapshot for `oldbook-cat status`, with no side effects at all."""
    if values is None:
        values = thermal.readings()
    if lid_shut is None:
        lid_shut = thermal.lid_closed()
    limits = thermal.regime(lid_shut is not False)
    state, reasons = thermal.verdict(values, limits)
    return {'lid': 'unknown' if lid_shut is None else ('closed' if lid_shut else 'open'),
            'regime': 'closed' if lid_shut is not False else 'open',
            'would': state, 'reasons': reasons,
            'unreadable': thermal.unreadable(values),
            'temperatures': {name: (None if value is None else round(value, 1))
                             for name, value in values.items()},
            'ceilings': {key: limits[key] for key in
                         ('cpu_target', 'cpu_ceiling', 'fan_release',
                          'battery_ceiling', 'skin_ceiling', 'abort')}}


if __name__ == '__main__':                                  # pragma: no cover
    print(json.dumps(describe(), indent=2))
