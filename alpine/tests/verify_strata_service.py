#!/usr/bin/env python3
"""Exercise STRATA supervision in private Sway with Fossil/browser fixtures."""

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

from verify_decoration_attachment import SwayIPC, walk


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "alpine/desktop/.local/bin/oldbook-strata"
BUS_MARKER = "OLDBOOK_STRATA_VERIFY_BUS"
APP = "oldbook-strata"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fixture(kind):
    """Only executable fixtures on this verifier's private PATH enter here."""
    require(os.environ.get(BUS_MARKER) == "1", "fixture requires private verifier bus")
    entry = {"kind": kind, "pid": os.getpid(), "ppid": os.getppid(), "args": sys.argv[1:]}
    with Path(os.environ["STRATA_VERIFY_TRACE"]).open("a") as trace:
        trace.write(json.dumps(entry) + "\n")
    if kind == "firefox":
        require(os.environ.get("MOZ_APP_REMOTINGNAME") == APP, "incorrect STRATA app identity")
        os.execv("/usr/bin/foot", ["foot", "--config", os.environ["STRATA_VERIFY_FOOT"],
                  "--app-id", APP, "--title", "Private STRATA service fixture",
                  "sh", "-c", "sleep 120"])
    port = sys.argv[sys.argv.index("--port") + 1]
    require(port.startswith("127.0.0.1:") and port != "127.0.0.1:8766",
            "Fossil fixture must use private loopback port")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Private alpine-oldbook Fossil fixture")

        def log_message(self, *_args):
            pass

    HTTPServer(("127.0.0.1", int(port.rsplit(":", 1)[1])), Handler).serve_forever()


def run_verifier(output, abrupt_shutdown=False):
    output.mkdir(parents=True, exist_ok=False)
    checks = []
    evidence = {"status": "running", "checks": checks, "host_changes": 0,
                "isolation": "private HOME, XDG directories, D-Bus, Sway and HTTP port",
                "external_fixtures": "Fossil HTTP fixture and Foot with exact browser app_id"}
    evidence["shutdown"] = "abrupt" if abrupt_shutdown else "graceful"
    sources = [HELPER, HELPER.with_name("oldbook-workspaces"),
               REPO / "alpine/desktop/.local/lib/oldbook/workspace_model.py"]
    hashes = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sources}
    evidence["source_sha256"] = hashes
    evidence["verifier_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    processes = []
    connection = None
    with tempfile.TemporaryDirectory(prefix="strata-service-") as directory:
        base = Path(directory)
        env = dict(os.environ)
        for key, name in (("HOME", "home"), ("XDG_RUNTIME_DIR", "run"),
                          ("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"),
                          ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data")):
            path = base / name
            path.mkdir(mode=0o700)
            env[key] = str(path)
        for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY"):
            env.pop(key, None)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        require(port != 8766, "private port overlaps host STRATA")
        env.update(WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1",
                   OLDBOOK_STRATA_PORT=str(port), NO_AT_BRIDGE="1", GTK_USE_PORTAL="0",
                   STRATA_VERIFY_TRACE=str(output / "fixtures.jsonl"),
                   STRATA_VERIFY_FOOT=str(base / "foot.ini"))
        evidence["private_port"] = port
        (base / "foot.ini").write_text("[main]\nfont=monospace:size=10\n")
        local_bin = base / "bin"
        local_bin.mkdir()
        for name in ("fossil", "firefox"):
            wrapper = local_bin / name
            wrapper.write_text("#!/usr/bin/env python3\nimport runpy,sys\n"
                               f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
                               f"runpy.run_path({str(Path(__file__).resolve())!r}, "
                               f"run_name='strata_fixture')['fixture']({name!r})\n")
            wrapper.chmod(0o755)
        env["PATH"] = str(local_bin) + os.pathsep + env["PATH"]
        repository = Path(env["HOME"]) / ".local/share/fossil/files.fossil"
        repository.parent.mkdir(parents=True)
        repository.write_text("Private fixture; never opened by real Fossil.\n")
        config = output / "sway.conf"
        config.write_text("xwayland disable\noutput HEADLESS-1 mode 1000x700\n"
                          "output * bg #13091f solid_color\nseat seat0 fallback true\n"
                          "focus_follows_mouse no\nworkspace 2\n"
                          'assign [app_id="^oldbook-strata$"] workspace number 10\n'
                          'no_focus [app_id="^oldbook-strata$"]\n')
        log = (output / "runtime.log").open("w")

        def spawn(name, command):
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
            processes.append((name, process))
            return process

        def wait_for(predicate, message, seconds=12):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                value = predicate()
                if value:
                    return value
                time.sleep(0.05)
            raise AssertionError(message)

        def ipc(kind=4, command=""):
            response = connection.requests([(kind, command)])[0]
            if kind == 0:
                require(response and all(item.get("success") for item in response),
                        f"private Sway command failed: {command}: {response!r}")
            return response

        def views():
            result = []
            for workspace in walk(ipc()):
                if workspace.get("type") != "workspace":
                    continue
                for view in walk(workspace):
                    if view.get("app_id"):
                        result.append({"id": view["id"], "app_id": view["app_id"],
                                       "workspace": workspace["num"],
                                       "focused": view.get("focused", False)})
            return result

        def browser():
            matches = [item for item in views() if item["app_id"] == APP]
            return matches[0] if len(matches) == 1 and matches[0]["workspace"] == 10 else None

        def fixtures(kind):
            path = output / "fixtures.jsonl"
            return [item for line in path.read_text().splitlines()
                    if (item := json.loads(line))["kind"] == kind] if path.exists() else []

        def ordinary_unchanged(identifier):
            return any(item["id"] == identifier and item["workspace"] == 2
                       and item["focused"] for item in views())

        def check(name):
            checks.append(name)
            (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")

        try:
            sway = spawn("sway", ["swayfx", "-c", str(config)])

            def ready():
                runtime = Path(env["XDG_RUNTIME_DIR"])
                sockets = list(runtime.glob("sway-ipc*.sock"))
                displays = [item for item in runtime.glob("wayland-*") if item.is_socket()]
                return (sockets[0], displays[0]) if sockets and displays else None

            sway_socket, display = wait_for(ready, "private Sway did not start")
            env["SWAYSOCK"], env["WAYLAND_DISPLAY"] = str(sway_socket), display.name
            connection = SwayIPC(sway_socket)
            spawn("ordinary-browser", ["/usr/bin/foot", "--config", str(base / "foot.ini"),
                  "--app-id", "firefox", "--title", "Ordinary Firefox control",
                  "sh", "-c", "sleep 120"])
            ordinary = wait_for(lambda: next((item for item in views()
                               if item["app_id"] == "firefox"), None), "ordinary browser missing")
            daemon = spawn("strata-daemon", [str(HELPER), "--daemon"])
            initial = wait_for(browser, "STRATA did not start on workspace 10")
            require(ordinary_unchanged(ordinary["id"]), "background startup stole browser focus")
            check("background-starts-on-ten-without-focus-steal")
            duplicate = spawn("duplicate-daemon", [str(HELPER), "--daemon"])
            require(duplicate.wait(timeout=4) == 0, "duplicate daemon did not exit successfully")
            require(len(fixtures("firefox")) == len(fixtures("fossil")) == 1,
                    "duplicate daemon launched extra browser/server")
            check("duplicate-daemon-keeps-one-browser-and-server")
            ipc(0, f'[con_id={initial["id"]}] move container to workspace number 4')
            wait_for(browser, "STRATA was not returned from workspace 4 to 10")
            require(ordinary_unchanged(ordinary["id"]), "pinning STRATA affected ordinary Firefox")
            check("moved-strata-returns-to-ten-ordinary-firefox-unchanged")
            launchers = [spawn(f"launcher-{number}", [str(HELPER)]) for number in range(2)]
            require(all(item.wait(timeout=15) == 0 for item in launchers), "explicit launcher failed")
            focused = wait_for(lambda: (item if (item := browser()) and item["focused"] else None),
                               "explicit launcher did not focus STRATA")
            require(focused["id"] == initial["id"] and len(fixtures("firefox")) == 1,
                    "concurrent launchers duplicated the browser")
            check("concurrent-launchers-focus-and-reuse-existing-browser")
            subprocess.run(["grim", "-o", "HEADLESS-1", str(output / "strata-workspace-ten.png")],
                           env=env, check=True, timeout=5)
            ipc(0, f'[con_id={ordinary["id"]}] focus; [con_id={initial["id"]}] kill')
            replacement = wait_for(lambda: (item if (item := browser())
                                   and item["id"] != initial["id"] else None),
                                   "service did not relaunch closed browser", seconds=20)
            require(ordinary_unchanged(ordinary["id"]), "browser relaunch stole focus")
            require(len(fixtures("firefox")) == 2 and len(fixtures("fossil")) == 1,
                    "browser recovery duplicated browser or Fossil")
            check("browser-relaunches-on-ten-without-focus-steal")
            evidence["final_views"] = views()
            evidence["replacement_id"] = replacement["id"]
            if abrupt_shutdown:
                sway.kill()
                require(sway.wait(timeout=5) == -signal.SIGKILL, "private compositor was not killed")
                require(sway_socket.is_socket(), "SIGKILL fixture did not leave a stale Sway socket")
                evidence["stale_socket_after_compositor_death"] = True
            else:
                try:
                    ipc(0, "exit")
                except ConnectionError:
                    # Sway can close IPC before writing the exit command's reply.
                    # Both process exit codes below still have to prove shutdown.
                    pass
                require(sway.wait(timeout=5) == 0, "private compositor did not stop")
            require(daemon.wait(timeout=12) == 0, "STRATA service did not stop with its session")

            def fixtures_stopped():
                identifiers = {entry[key] for entry in fixtures("fossil") + fixtures("firefox")
                               for key in ("pid", "ppid")}
                for identifier in identifiers:
                    try:
                        state = Path(f'/proc/{identifier}/stat').read_text().split(') ', 1)[1].split()[0]
                        if state != "Z":
                            return False
                    except FileNotFoundError:
                        pass
                return True

            wait_for(fixtures_stopped, "STRATA browser/Fossil survived session shutdown")
            check("abrupt-session-shutdown-cleans-service-with-stale-socket" if abrupt_shutdown
                  else "session-shutdown-cleans-service-browser-and-server")
            if abrupt_shutdown:
                counts = (len(fixtures("firefox")), len(fixtures("fossil")))
                stale_start = spawn("stale-session-daemon", [str(HELPER), "--daemon"])
                require(stale_start.wait(timeout=4) == 0, "service kept retrying an initially stale socket")
                require((len(fixtures("firefox")), len(fixtures("fossil"))) == counts,
                        "stale session started browser or Fossil children")
                check("initially-stale-socket-exits-without-launching-children")
            require(all(hashlib.sha256((REPO / name).read_bytes()).hexdigest() == digest
                        for name, digest in hashes.items()), "STRATA source changed during verification")
            evidence["status"] = "passed"
        except BaseException as error:
            evidence["status"], evidence["error"] = "failed", str(error)
            raise
        finally:
            if connection:
                connection.close()
            for _name, process in reversed(processes):
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
            # Service children can create their own sessions. On failure, only
            # target traced fixture PIDs still carrying this private runtime.
            marker = ("XDG_RUNTIME_DIR=" + env["XDG_RUNTIME_DIR"]).encode()
            identifiers = {entry[key] for entry in fixtures("fossil") + fixtures("firefox")
                           for key in ("pid", "ppid")}
            for identifier in identifiers:
                try:
                    if marker in Path(f'/proc/{identifier}/environ').read_bytes().split(b"\0"):
                        os.kill(identifier, signal.SIGKILL)
                except (FileNotFoundError, ProcessLookupError):
                    pass
            service_log = Path(env["HOME"]) / ".local/state/oldbook/strata.log"
            if service_log.exists():
                (output / "service.log").write_bytes(service_log.read_bytes())
            log.close()
            (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--abrupt-shutdown", action="store_true",
                        help="kill the private compositor and verify cleanup despite its stale socket")
    args = parser.parse_args()
    if os.environ.get(BUS_MARKER) != "1":
        env = dict(os.environ)
        env.pop("DBUS_SESSION_BUS_ADDRESS", None)
        env[BUS_MARKER] = "1"
        os.execvpe("dbus-run-session", ["dbus-run-session", "--", sys.executable,
                    str(Path(__file__).resolve()), *sys.argv[1:]], env)
    require("DBUS_SESSION_BUS_ADDRESS" in os.environ, "private D-Bus missing")
    run_verifier(args.output.resolve(), args.abrupt_shutdown)


if __name__ == "__main__":
    main()
