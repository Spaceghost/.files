"""One explicit command interface for desktop and system protection stages."""

import argparse
import json
import sys

from . import __version__


def parser():
    result = argparse.ArgumentParser(
        prog="catbed",
        description="Park input for a cat. This is not an authentication lock.",
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities", help="describe support without changing the machine")
    commands.add_parser("start", help="park desktop input until deliberately released")
    commands.add_parser("stop", help="release the desktop guard")
    commands.add_parser("status", help="report the desktop guard's current state")
    export = commands.add_parser("export-system", help="extract packaged system files without installing them")
    export.add_argument("destination", help="new directory to create; existing paths are refused")
    system = commands.add_parser("system", help="control the separate privileged boot stage")
    system.add_argument("action", choices=("run", "status", "recover", "shutdown"))
    system.add_argument("--user", help="desktop user for boot-to-session handoff (run only)")
    return result


def main(argv=None):
    arguments = parser().parse_args(argv)
    if arguments.command == "system" and arguments.user and arguments.action != "run":
        parser().error("--user is only valid with system run")
    if sys.platform != "linux":
        if arguments.command == "capabilities":
            print(json.dumps({
                "platform": sys.platform,
                "supported": False,
                "reason": "Only the Linux backend is implemented. No input is protected.",
            }, indent=2))
            return 0
        print("catbed: this platform has no implemented backend; input is unchanged", file=sys.stderr)
        return 2

    # Platform-specific imports must stay below dispatch. Windows and macOS
    # can inspect package metadata without importing Linux or GTK modules.
    from .linux import capabilities, execute

    if arguments.command == "capabilities":
        print(json.dumps(capabilities(), indent=2))
        return 0
    try:
        if arguments.command == "export-system":
            from .system_resources import export

            print(export(arguments.destination))
            return 0
        return execute(arguments)
    except (OSError, RuntimeError) as error:
        print(f"catbed: {error}", file=sys.stderr)
        return 1
