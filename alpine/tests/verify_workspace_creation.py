#!/usr/bin/env python3
"""Check workspace names at native Sway creation without a naming daemon."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time

from verify_decoration_attachment import SwayIPC, walk


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "alpine/desktop/.config/sway/config"
NAMES = {1: "Ghost", 2: "Orbit", 3: "Lab", 4: "Signal", 5: "Lounge", 10: "Strata"}
BUS_MARKER = "OLDBOOK_WORKSPACE_CREATION_PRIVATE_BUS"
MAGIC = b"i3-ipc"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class WorkspaceEvents:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(4)
        self.socket.connect(str(path))
        self.send(2, '["workspace"]')
        kind, reply = self.read()
        require(kind == 2 and reply.get("success"), "workspace subscription failed")

    def send(self, kind, payload=""):
        data = payload.encode()
        self.socket.sendall(MAGIC + struct.pack("<II", len(data), kind) + data)

    def exact(self, length):
        deadline = time.monotonic() + 4
        result = bytearray()
        while len(result) < length:
            self.socket.settimeout(max(.001, deadline - time.monotonic()))
            chunk = self.socket.recv(length - len(result))
            require(chunk, "workspace event socket closed")
            result.extend(chunk)
            require(time.monotonic() < deadline, "workspace event read timed out")
        return bytes(result)

    def read(self):
        header = self.exact(14)
        require(header[:6] == MAGIC, "invalid workspace event header")
        length, kind = struct.unpack("<II", header[6:])
        require(length <= 16 * 1024 * 1024, "oversized workspace event")
        return kind, json.loads(self.exact(length))

    def drain(self):
        # GET_WORKSPACES on the subscribed stream is a barrier after the
        # command's reply; retain every preceding workspace event in order.
        self.send(1)
        result = []
        deadline = time.monotonic() + 4
        while True:
            require(time.monotonic() < deadline and len(result) < 10000,
                    "workspace event barrier timed out")
            kind, event = self.read()
            if kind == 1:
                return result
            require(kind == 0x80000000, "unexpected event on workspace stream")
            entry = {"change": event["change"]}
            for key in ("current", "old"):
                workspace = event.get(key)
                entry[key] = ({name: workspace.get(name) for name in ("id", "num", "name")}
                              if workspace else None)
            result.append(entry)

    def close(self):
        self.socket.close()


def bindings(source):
    result = {}
    for line in source.splitlines():
        match = re.fullmatch(r"bindsym\s+\$mod\+((?:Shift\+)?[0-9])\s+(.+)", line.strip())
        if match and re.match(r"(?:move container to )?workspace number ", match[2]):
            result[match[1]] = match[2]
    for number in range(1, 10):
        require(str(number) in result and f"Shift+{number}" in result,
                f"missing direct workspace binding {number}")
    require("Shift+0" in result, "missing direct workspace-10 move binding")
    return result


def run(output, source_config):
    source = source_config.read_bytes()
    commands = bindings(source.decode())
    rules = [line.strip() for line in source.decode().splitlines()
             if line.strip().startswith(('assign [app_id="^oldbook-strata$"] ',
                                         'no_focus [app_id="^oldbook-strata$"]'))]
    require(len(rules) == 2, "missing exact STRATA assignment/focus rules")
    library = REPO / "alpine/desktop/.local/lib/oldbook"
    sources = [library / name for name in ("expo.py", "showdesktop.py", "workspace_model.py")]
    workspace_service = REPO / "alpine/desktop/.local/bin/oldbook-workspaces"
    sources.append(workspace_service)
    sources.append(Path(__file__).with_name("verify_decoration_attachment.py"))
    hashes = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sources}
    launchers = {"expo": runpy.run_path(str(library / "expo.py"))["focus_command"],
                 "showdesktop": runpy.run_path(str(library / "showdesktop.py"))["switch_command"]}
    rename_workspace = runpy.run_path(str(workspace_service))["rename"]
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"status": "running", "source_config_sha256": hashlib.sha256(source).hexdigest(),
                "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "bindings": commands, "rules": rules, "source_sha256": hashes,
                "checks": [], "scenarios": {}, "host_changes": 0,
                "naming_daemon_started": False,
                "isolation": "private Sway, HOME, XDG directories and D-Bus; synthetic Foot window"}
    processes = []
    ipc = events = None
    with tempfile.TemporaryDirectory(prefix="workspace-creation-") as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, name in (("HOME", "home"), ("XDG_RUNTIME_DIR", "run"),
                          ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                          ("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache")):
            path = base / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY"):
            env.pop(key, None)
        env.update(WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1", NO_AT_BRIDGE="1")
        config = output / "sway.conf"
        config.write_text("xwayland disable\noutput HEADLESS-1 mode 1000x700\n"
                          "output * bg #13091f solid_color\nseat seat0 fallback true\n"
                          "focus_follows_mouse no\nworkspace 99: Control\n" +
                          "\n".join(f"bindsym Mod4+{key} {command}" for key, command in commands.items()) +
                          "\n" + "\n".join(rules) + "\n")
        (base / "foot.ini").write_text("[main]\nfont=monospace:size=10\n")
        log = (output / "runtime.log").open("w")

        def spawn(command):
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
            processes.append(process)
            return process

        def wait_for(predicate, message):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if value := predicate():
                    return value
                time.sleep(.025)
            raise AssertionError(message)

        def request(kind=4, command=""):
            return ipc.requests([(kind, command)])[0]

        def command(text):
            reply = request(0, text)
            require(reply and all(item.get("success") for item in reply), f"Sway rejected {text!r}")
            return events.drain()

        def check(name, passed):
            evidence["checks"].append({"name": name, "passed": bool(passed)})

        def named_creation(name, observed, number, focus):
            expected = f"{number}: {NAMES[number]}"
            relevant = [item for item in observed if item["change"] in ("init", "focus")
                        and item["current"] and item["current"]["num"] == number]
            evidence["scenarios"][name] = observed
            changes = [item["change"] for item in relevant]
            check(name, bool(relevant) and changes[0] == "init" and
                  (not focus or "focus" in changes) and
                  all(item["current"]["name"] == expected for item in relevant))

        try:
            sway = spawn(["swayfx", "-c", str(config)])

            def ready():
                runtime = Path(env["XDG_RUNTIME_DIR"])
                sockets = list(runtime.glob("sway-ipc.*.sock"))
                displays = [path for path in runtime.glob("wayland-*") if path.is_socket()]
                return (sockets[0], displays[0]) if sockets and displays else None

            sway_socket, display = wait_for(ready, "private Sway did not start")
            env.update(SWAYSOCK=str(sway_socket), WAYLAND_DISPLAY=display.name)
            ipc, events = SwayIPC(sway_socket), WorkspaceEvents(sway_socket)
            for number in range(1, 6):
                observed = command(commands[str(number)])
                named_creation(f"focus-{number}-named-from-init", observed, number, True)
                command('workspace number "99: Control"')
            evidence["launcher_commands"] = {}
            for name, focus_command in launchers.items():
                for number in (4, 10):
                    text = focus_command({"num": number})
                    key = f"{name}-{number}-named-from-init"
                    evidence["launcher_commands"][key] = text
                    named_creation(key, command(text), number, True)
                    command('workspace number "99: Control"')

            spawn(["/usr/bin/foot", "--config", str(base / "foot.ini"),
                   "--app-id", "workspace-creation-fixture", "--title", "Private workspace creation fixture",
                   "sh", "-c", "sleep 120"])
            window = wait_for(lambda: next((item for item in walk(request())
                              if item.get("app_id") == "workspace-creation-fixture"), None),
                              "private window did not map")
            events.drain()
            for number, key in ((4, "Shift+4"), (10, "Shift+0")):
                observed = command(commands[key])
                named_creation(f"move-{number}-named-from-init", observed, number, False)
                destination = commands[key].removeprefix("move container to ")
                focused = command(destination)
                evidence["scenarios"][f"focus-existing-{number}"] = focused
                expected = f"{number}: {NAMES[number]}"
                relevant = [item for item in focused if item["change"] == "focus"
                            and item["current"] and item["current"]["num"] == number]
                check(f"focus-existing-{number}-keeps-name", relevant and
                      all(item["current"]["name"] == expected for item in relevant))
                command('move container to workspace number "99: Control"; workspace number "99: Control"')

            command('workspace number "4: My Custom Label"')
            command(f'[con_id={window["id"]}] move container to workspace number 4')
            custom = next(item for item in request(1) if item["num"] == 4)
            command('workspace number "99: Control"')
            observed = command(commands["4"])
            existing = [item for item in request(1) if item["num"] == 4]
            evidence["scenarios"]["custom-four-revisit"] = observed
            check("custom-four-reused-without-rename-or-duplicate", len(existing) == 1 and
                  existing[0]["id"] == custom["id"] and existing[0]["name"] == "4: My Custom Label" and
                  not any(item["change"] in ("init", "rename") and item["current"] and
                          item["current"]["num"] == 4 for item in observed))
            old_name, new_name = "4: SIGNAL · Café Δοκιμή", "4: Signal · Café Δοκιμή"
            command('rename workspace "4: My Custom Label" to ' + json.dumps(old_name, ensure_ascii=False))
            before = request(1)
            rename_workspace(sway_socket, old_name, new_name)
            observed = events.drain()
            after = request(1)
            existing = [item for item in after if item["num"] == 4]
            workspace = next((item for item in walk(request())
                              if item.get("type") == "workspace" and item.get("id") == custom["id"]), {})
            evidence["scenarios"]["existing-uppercase-migration"] = observed
            evidence["case_only_rename"] = {
                "old_name": old_name, "requested_name": new_name, "call_returned_without_error": True,
                "before": [{key: item[key] for key in ("id", "num", "name")} for item in before],
                "after": [{key: item[key] for key in ("id", "num", "name")} for item in after]}
            check("existing-uppercase-migrates-with-same-workspace-and-window", len(existing) == 1 and
                  existing[0]["id"] == custom["id"] and existing[0]["name"] == new_name and
                  {item["id"] for item in before} == {item["id"] for item in after} and
                  any(item.get("id") == window["id"] for item in walk(workspace)))
            subprocess.run(["grim", "-o", "HEADLESS-1", str(output / "workspace-creation.png")],
                           env=env, check=True, timeout=5)
            command('move container to workspace number "99: Control"; workspace number "99: Control"')
            spawn(["/usr/bin/foot", "--config", str(base / "foot.ini"),
                   "--app-id", "oldbook-strata", "--title", "Private STRATA assignment fixture",
                   "sh", "-c", "sleep 120"])
            wait_for(lambda: next((item for item in walk(request())
                     if item.get("app_id") == "oldbook-strata"), None), "private STRATA window did not map")
            named_creation("strata-assignment-named-from-init", events.drain(), 10, False)
            workspaces = request(1)
            check("strata-background-assignment-preserves-control-focus",
                  any(item["num"] == 99 and item["focused"] for item in workspaces))
            evidence["final_workspaces"] = [{key: item[key] for key in ("id", "num", "name", "focused")}
                                             for item in workspaces]
            require(source_config.read_bytes() == source, "source config changed during verification")
            require(all(hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest
                        for name, digest in hashes.items()), "launcher source changed during verification")
            failures = [item["name"] for item in evidence["checks"] if not item["passed"]]
            evidence["failures"] = failures
            require(not failures, "workspace names failed: " + ", ".join(failures))
            evidence["status"] = "passed"
        except BaseException as error:
            evidence.update(status="failed", error=str(error))
            raise
        finally:
            if events:
                events.close()
            if ipc:
                ipc.close()
            for process in reversed(processes):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            log.close()
            (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    if os.environ.get(BUS_MARKER) != "1":
        env = dict(os.environ)
        env.pop("DBUS_SESSION_BUS_ADDRESS", None)
        env[BUS_MARKER] = "1"
        os.execvpe("dbus-run-session", ["dbus-run-session", "--", sys.executable,
                    str(Path(__file__).resolve()), *sys.argv[1:]], env)
    require("DBUS_SESSION_BUS_ADDRESS" in os.environ, "private D-Bus missing")
    run(args.output.resolve(), args.config.resolve())


if __name__ == "__main__":
    main()
