"""A failed run's notification, with the whole log one click behind it.

Notifications about failures arrive while nobody is watching, and by the time
they are read the run is long over. Saying the reason is half of it; the other
half is that the reason is a summary, and the answer to "why" is often two
lines further down the log than a notification can carry.

``notify-send`` can attach an action, but doing so implies waiting: the process
that sends the notification stays alive until the user clicks it or dismisses
it. A generator cannot wait around like that -- it has a painting to finish or
a failure to exit with -- so the waiting is handed to a detached child of this
module, which outlives its parent, does nothing but hold the notification, and
opens the log if the button is pressed.

Nothing here is on the critical path. Every failure to notify, to spawn, or to
find a terminal is swallowed: a desktop that cannot show the message must not
also lose the exit status of the thing that failed.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

APP_NAME = 'Ghost Gallery'
ACTION = 'open'
ACTION_LABEL = 'Show the whole run'
# Terminals in the order this desktop would reach for one, then whatever the
# session has set. Foot is first because it is the one the system monitor uses
# and it starts in a fraction of the time a GPU terminal does.
TERMINALS = ('foot', 'ghostty', 'xterm')


def pager_command(log):
    """A terminal showing the log, or None when there is no terminal to use."""
    for name in (*TERMINALS, os.environ.get('TERMINAL') or ''):
        if not name or not shutil.which(name):
            continue
        title = ['--title=Ghost Gallery — the whole run']
        if name == 'ghostty':
            title = ['--title=Ghost Gallery — the whole run']
        elif name == 'xterm':
            title = ['-T', 'Ghost Gallery — the whole run']
        viewer = 'less' if shutil.which('less') else 'cat'
        arguments = ['-R', '+G', os.fspath(log)] if viewer == 'less' else [os.fspath(log)]
        separator = ['-e'] if name in ('ghostty', 'xterm') else []
        return [name, *title, *separator, viewer, *arguments]
    return None


def open_log(log):
    command = pager_command(log)
    if command is None:
        return False
    try:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True


def session_environment():
    env = os.environ.copy()
    runtime = Path('/run/user') / str(os.getuid())
    if 'DBUS_SESSION_BUS_ADDRESS' not in env and (runtime / 'bus').exists():
        env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(runtime / 'bus')
    return env


def hold(title, message, log, urgency='critical'):
    """Show the notification and wait, opening the log if the button is pressed.

    This blocks, which is why callers reach it through ``announce``.
    """
    command = ['notify-send', '--app-name=' + APP_NAME, '--icon=image-x-generic',
               '--urgency=' + urgency]
    if log is not None:
        command.append(f'--action={ACTION}={ACTION_LABEL}')
    try:
        result = subprocess.run([*command, '--', title, message], env=session_environment(),
                                capture_output=True, text=True, timeout=86400)
    except (OSError, subprocess.SubprocessError):
        return False
    if log is not None and result.stdout.strip() == ACTION:
        return open_log(log)
    return True


def announce(title, message, log):
    """Send the notification from a detached child and return immediately."""
    try:
        subprocess.Popen([sys.executable, os.fspath(Path(__file__).resolve()),
                          '--title', title, '--message', message,
                          *(['--log', os.fspath(log)] if log is not None else [])],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--title', required=True)
    parser.add_argument('--message', required=True)
    parser.add_argument('--log')
    arguments = parser.parse_args(argv)
    hold(arguments.title, arguments.message, arguments.log)
    return 0


if __name__ == '__main__':
    sys.exit(main())
