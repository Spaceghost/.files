"""Linux stage adapter during migration of the existing guard implementation.

The guard remains responsible for proving keyboard ownership and reporting
its actual state. Finding an executable is never evidence that input is held.
"""

import os
from pathlib import Path
import stat
import sys


SYSTEM_HELPER = Path("/usr/local/sbin/oldbook-catmode")


def desktop_helper():
    helper = Path(__file__).resolve().parent / "runtime/alpine/desktop/.local/bin/oldbook-watch"
    return str(helper) if helper.is_file() else None


def capabilities():
    return {
        "platform": "linux",
        "desktop_backend": "sway-wayland",
        "supported": True,
        "implementation": "bundled-sway-wayland-guard",
        "desktop_runtime_bundled": desktop_helper() is not None,
        "self_contained": False,
        "desktop": {
            "helper": desktop_helper(),
            "requirements": ["Sway", "Wayland", "GTK4", "GTK4 layer-shell", "PyGObject"],
            "persists_across_lock": True,
            "release": "Hold Super+Shift+Escape for one second with no other key down",
        },
        "system": {
            "helper": str(SYSTEM_HELPER),
            "installed": SYSTEM_HELPER.is_file(),
            "earliest_stage": "OpenRC after local filesystems are mounted",
            "firmware_protection": False,
            "encrypted_disk_prompt_protection": False,
            "fan_control": "Optional hardware-specific helper with thermal override",
        },
        "input_held": "Unknown: use status; capabilities does not start or prove protection",
    }


def execute(arguments):
    if arguments.command != "system":
        if os.geteuid() == 0:
            raise RuntimeError("run desktop commands as the desktop user, not root")
        if arguments.command == "start" and (
            not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("SWAYSOCK")
        ):
            raise RuntimeError("start requires the current Sway Wayland session; no X11 fallback is implemented")
        helper = desktop_helper()
        if helper is None:
            raise RuntimeError(
                "the bundled desktop runtime is missing; "
                "use a built Catbed distribution rather than an editable source install"
            )
        command = [sys.executable, helper, arguments.command]
    else:
        info = SYSTEM_HELPER.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError(f"{SYSTEM_HELPER} must be a root-owned, unwritable regular file")
        if arguments.action != "status" and os.geteuid() != 0:
            raise RuntimeError("system mutations require root; privileges are never elevated automatically")
        command = [str(SYSTEM_HELPER), arguments.action]
        if arguments.action == "run":
            if not arguments.user:
                raise RuntimeError("system run requires --user for the desktop handoff")
            command += ["--user", arguments.user]

    # Replace the adapter rather than supervising it: signals, exit status,
    # inhibitor pipe lifetimes, and service-manager PID identity stay intact.
    os.execv(command[0], command)
