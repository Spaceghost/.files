"""Request desktop scheduling once at daemon startup, away from input callbacks."""
import os
from pathlib import Path
import subprocess
import threading


def request_priority():
    helper = Path('/usr/local/sbin/mbp-intel-ui-priority')
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    sway = os.environ.get('SWAYSOCK')
    if (not helper.is_file() or not runtime or not sway
            or Path(sway).parent != Path(runtime) or not Path(sway).is_socket()):
        return
    try:
        process = subprocess.Popen(['/usr/bin/doas', '-n', str(helper), '--session', sway,
                                    str(os.getpid())], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True, close_fds=True)
        threading.Thread(target=process.wait, name='ui-priority-reaper', daemon=True).start()
    except OSError:
        # Missing privilege support must never prevent the UI from starting.
        pass
