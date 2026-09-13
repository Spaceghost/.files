"""What holds the machine still while its input is parked.

Two things park input on this desktop: the screen lock, `oldbook-lock`, and
catbed mode, `oldbook-watch` on Super+Shift+Escape. While either is up nothing
a cat can press may shut the machine down or put it to sleep, and this module
is the one place that says what that takes:

  the keys   A block inhibitor with the login manager -- elogind here, systemd
             on the Bazzite replay -- on the power, suspend and hibernate keys.
             A press, a hold and every autorepeat of a held key are refused;
             elogind logs each one and does nothing else.
  SysRq      The kernel answers Alt+SysRq beneath every compositor and every
             inhibitor, so while input is parked its bitmask is narrowed by a
             root helper, `catbed-sysrq-hold`, and put back when the hold ends.

Both are held the way the lock has always held the power key: a process that
waits on a pipe, so the release is the pipe closing rather than anyone
remembering to release it, and it happens however the holder's tree ends. Both
are also optional in the same sense: a hold that is missing or refused is said
out loud, in the helper's own words, and is never a reason to leave input live.

What is held is the user's choice, in ~/.config/oldbook/catbed.json:

    {"version": 1,
     "keys": ["power", "suspend", "hibernate"],
     "sysrq": {"guard": true, "mask": 382}}

`keys` may also name "lid", and an empty list holds no key. `mask` is the
kernel.sysrq bitmask held while input is parked: 382 is every SysRq function
except reboot and power-off, so Alt+SysRq+S and +U can still sync and remount a
wedged machine before the hardware cut, and 0 switches the key off outright. A
missing or malformed file, or any one bad value, falls back to the shipped
default for that value alone.
"""
import json
import os
from pathlib import Path
import select
import shutil
import stat
import subprocess
import sys
import time

INHIBITORS = ('elogind-inhibit', 'systemd-inhibit')
KEYS = {'power': 'handle-power-key', 'suspend': 'handle-suspend-key',
        'hibernate': 'handle-hibernate-key', 'lid': 'handle-lid-switch'}
DEFAULT_KEYS = ('power', 'suspend', 'hibernate')
# Every SysRq function but reboot and power-off, which is bit 128.
DEFAULT_MASK = 382
MASK_LIMIT = 511
SYSRQ_HELPER = '/usr/local/sbin/catbed-sysrq-hold'
DOAS = 'doas'
# The helper prints this once the mask is written. A hold that never says so
# is not a hold, whatever doas was prepared to run.
HOLDING = 'holding'
CONFIRM_SECONDS = 3.0
APP = 'Catbed'


class Problem(str):
    """A hold that was wanted and not taken. A loud problem is announced on the
    desktop; a quiet one -- a host with no helper installed at all -- is only
    written to stderr, because a Bazzite session is not a broken one."""
    loud = True


class Quiet(Problem):
    loud = False


def config_path():
    override = os.environ.get('CATBED_GUARD_CONFIG')
    if override:
        return Path(override)
    root = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(root) / 'oldbook/catbed.json'


def settings(document=None):
    """The policy with every value checked; a bad one is its default instead."""
    result = {'version': 1, 'keys': list(DEFAULT_KEYS),
              'sysrq': {'guard': True, 'mask': DEFAULT_MASK}}
    if not isinstance(document, dict):
        return result
    keys = document.get('keys')
    if isinstance(keys, list) and all(isinstance(key, str) and key in KEYS for key in keys):
        result['keys'] = list(dict.fromkeys(keys))
    sysrq = document.get('sysrq')
    if isinstance(sysrq, dict):
        if isinstance(sysrq.get('guard'), bool):
            result['sysrq']['guard'] = sysrq['guard']
        mask = sysrq.get('mask')
        if isinstance(mask, int) and not isinstance(mask, bool) and 0 <= mask <= MASK_LIMIT:
            result['sysrq']['mask'] = mask
    return result


def load_settings(path=None):
    try:
        return settings(json.loads((Path(path) if path else config_path()).read_text()))
    except (OSError, ValueError):
        return settings()


def inhibit_arguments(keys, who, why):
    """The login manager's own vocabulary for the keys the policy names."""
    return [f'--what={":".join(KEYS[key] for key in keys)}', '--mode=block',
            f'--who={who}', f'--why={why}', '--', 'cat']


def _first_line(stream, timeout):
    deadline = time.monotonic() + timeout
    buffer = b''
    while b'\n' not in buffer:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        readable, _, _ = select.select([stream], [], [], remaining)
        if not readable:
            break
        chunk = os.read(stream.fileno(), 4096)
        if not chunk:
            break
        buffer += chunk
    return buffer.split(b'\n', 1)[0].decode(errors='replace').strip()


def pipe_holder(command, confirm=None, timeout=CONFIRM_SECONDS):
    """Run `command` reading a pipe; return the pipe's write end.

    The command lives until every copy of the returned descriptor is closed,
    so the caller keeps it, or hands it to a process tree, for exactly as long
    as the hold should last. With `confirm`, the command must print that line
    before the hold counts: doas is happy to start a helper that then refuses,
    and a hold believed in but never taken is the failure this exists to avoid.
    """
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(command, stdin=read_fd,
                                   stdout=subprocess.PIPE if confirm else subprocess.DEVNULL,
                                   stderr=subprocess.PIPE if confirm else subprocess.DEVNULL,
                                   start_new_session=True)
    except (OSError, ValueError, subprocess.SubprocessError):
        os.close(write_fd)
        raise
    finally:
        os.close(read_fd)
    if not confirm:
        return write_fd
    try:
        line = _first_line(process.stdout, timeout)
        if line != confirm:
            error = ''
            if process.poll() is not None or select.select([process.stderr], [], [], 0.2)[0]:
                error = os.read(process.stderr.fileno(), 4096).decode(errors='replace').strip()
            raise RuntimeError(error or line or f'{Path(command[0]).name} never said {confirm!r}')
    except BaseException:
        os.close(write_fd)
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
    return write_fd


def hold_keys(who, why, policy=None):
    """Keep the login manager off the configured keys: (descriptor, problem).

    (None, None) is the user's own choice of holding no key; (None, text) is a
    hold that was wanted and could not be taken.
    """
    policy = load_settings() if policy is None else policy
    if not policy['keys']:
        return None, None
    inhibitor = next(filter(None, map(shutil.which, INHIBITORS)), None)
    if inhibitor is None:
        return None, Problem('the keys stay live: neither elogind-inhibit nor systemd-inhibit is installed')
    try:
        return pipe_holder([inhibitor] + inhibit_arguments(policy['keys'], who, why)), None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return None, Problem(f'the keys stay live: {Path(inhibitor).name} did not start ({error})')


def sysrq_helper_command(mask):
    """How to run the SysRq hold: through doas, unless a test aims elsewhere.

    The same rule as the fan hold: a root process must not be a file the user
    can rewrite, so the installed helper must be root-owned and neither group
    nor world writable before it is run. CATBED_SYSRQ_HELPER names a test's
    own unprivileged copy, aimed at its own sysrq file and state directory.
    """
    override = os.environ.get('CATBED_SYSRQ_HELPER')
    if override:
        command = [sys.executable, override, 'hold', '--mask', str(int(mask))]
        for variable, option in (('CATBED_SYSRQ_PATH', '--path'), ('CATBED_SYSRQ_STATE', '--state')):
            if os.environ.get(variable):
                command += [option, os.environ[variable]]
        return command, None
    path = Path(SYSRQ_HELPER)
    try:
        info = path.stat()
    except OSError:
        return None, Quiet(f'{path} is not installed; doas alpine/bin/install-catbed-guard installs it')
    if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return None, Problem(f'{path} is not a root-owned, unwritable file')
    if shutil.which(DOAS) is None:
        return None, Problem('doas is not installed')
    return [DOAS, '-n', str(path), 'hold', '--mask', str(int(mask))], None


def hold_sysrq(policy=None):
    """Narrow SysRq through the root helper: (descriptor, problem)."""
    policy = load_settings() if policy is None else policy
    if not policy['sysrq']['guard']:
        return None, None
    command, problem = sysrq_helper_command(policy['sysrq']['mask'])
    if command is None:
        return None, type(problem)(f'SysRq stays live: {problem}')
    try:
        return pipe_holder(command, confirm=HOLDING), None
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        return None, Problem(f'SysRq stays live: {error}')


def hold_all(who, why, policy=None):
    """Every hold the policy asks for: (descriptors, problems). Never raises,
    and one hold failing never costs the others."""
    policy = load_settings() if policy is None else policy
    descriptors, problems = [], []
    for descriptor, problem in (hold_keys(who, why, policy), hold_sysrq(policy)):
        if descriptor is not None:
            descriptors.append(descriptor)
        if problem:
            problems.append(problem)
    return descriptors, problems


def release(descriptors):
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass


def announce(summary, problems):
    """A hold that could not be taken is said out loud, in the helper's own
    words: the lock and catbed mode carry on without it, so this is the trace.
    Quiet problems reach stderr only."""
    body = '\n'.join(problems)
    print(f'{summary}: {body}', file=sys.stderr)
    if not any(getattr(problem, 'loud', True) for problem in problems):
        return
    try:
        subprocess.Popen(['notify-send', '-a', APP, '-u', 'critical', summary, body],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def describe(policy=None):
    policy = load_settings() if policy is None else policy
    keys = ', '.join(policy['keys']) or 'no keys'
    sysrq = (f'SysRq narrowed to {policy["sysrq"]["mask"]}' if policy['sysrq']['guard']
             else 'SysRq left alone')
    return f'while input is parked: {keys} held off; {sysrq}'
