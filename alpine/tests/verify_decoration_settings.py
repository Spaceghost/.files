#!/usr/bin/env python3
"""Exercise decoration preferences in a private headless SwayFX session."""

import argparse
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import traceback


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "alpine/desktop/.local/bin/mbp-intel-decoration-settings"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_client(source, config_home, state_home, output):
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    GLib.set_prgname("mbp-intel-decoration-settings")
    module = runpy.run_path(str(source), run_name="decoration_preferences")
    create_window = module["create_window"]
    create_window.__globals__["CONFIG"] = config_home
    create_window.__globals__["STATE"] = state_home
    config = config_home / "mbp-intel/decoration.json"
    legacy = state_home / "mbp-intel/decoration/position"
    save_settings = module["save_settings"]

    window = create_window(config)
    window.show_all()
    checks = []
    failures = []

    def read_config():
        return json.loads(config.read_text())

    def guarded(callback):
        def invoke():
            try:
                return callback()
            except BaseException as error:
                traceback.print_exc()
                failures.append(error)
                window.destroy()
                Gtk.main_quit()
                return False

        return invoke

    def exercise_initial_conflict():
        window.position.set_active_id("bottom")
        window.opacity.set_value(55)
        window.radius.set_value(12)
        external = {"position": "right", "opacity": 0.78, "corner_radius": 7}
        save_settings(config, external, legacy)
        window.apply_controls(None)
        require(read_config() == external, "stale controls overwrote an external update")
        require(
            "changed on disk" in window.status.get_text(),
            "stale controls did not explain why the save was blocked",
        )
        checks.append("external-change-blocks-stale-controls")
        GLib.timeout_add(250, guarded(capture_conflict_and_continue))
        return False

    def capture_conflict_and_continue():
        subprocess.run(
            ["grim", str(output / "conflict.png")], check=True, timeout=5
        )
        window.reload()
        require(window.position.get_active_id() == "right", "reload missed position")
        require(round(window.opacity.get_value()) == 78, "reload missed opacity")
        require(window.radius.get_value_as_int() == 7, "reload missed radius")
        require(
            json.loads(window.buffer.get_text(*window.buffer.get_bounds(), True))
            == read_config(),
            "reload did not synchronize the JSON editor",
        )
        checks.append("reload-applies-external-change")

        window.opacity.set_value(55)
        window.radius.set_value(12)
        window.apply_controls(None)
        controls_saved = {
            "position": "right",
            "opacity": 0.55,
            "corner_radius": 12,
        }
        require(read_config() == controls_saved, "controls did not save")
        require(
            json.loads(window.buffer.get_text(*window.buffer.get_bounds(), True))
            == controls_saved,
            "controls did not update the JSON editor",
        )
        checks.append("controls-save-and-update-json")
        require(legacy.read_text() == "right\n", "GUI save left legacy position stale")
        checks.append("legacy-position-follows-gui-save")

        original = config.read_bytes()
        window.buffer.set_text("{ broken JSON")
        window.apply_json(None)
        require(config.read_bytes() == original, "invalid JSON changed the saved file")
        require(
            "Could not apply JSON" in window.status.get_text(),
            "invalid JSON did not produce an error status",
        )
        checks.append("invalid-json-preserves-saved-file")

        json_saved = {"position": "bottom", "opacity": 0.78, "corner_radius": 7}
        window.buffer.set_text(json.dumps(json_saved))
        window.apply_json(None)
        require(read_config() == json_saved, "valid JSON did not save")
        require(
            window.position.get_active_id() == "bottom"
            and window.radius.get_value_as_int() == 7,
            "valid JSON did not update the controls",
        )
        checks.append("json-save-and-update-controls")

        original = config.read_bytes()
        window.buffer.set_text('{"opacity": false}')
        window.apply_json(None)
        require(config.read_bytes() == original, "invalid value changed the saved file")
        checks.append("invalid-value-preserves-saved-file")

        window.buffer.set_text(
            json.dumps({"position": "bottom", "opacity": 0.66, "corner_radius": 10})
        )
        external = {"position": "right", "opacity": 0.78, "corner_radius": 7}
        save_settings(config, external, legacy)
        window.apply_json(None)
        require(read_config() == external, "stale JSON overwrote an external update")
        require(
            "changed on disk" in window.status.get_text(),
            "stale JSON did not explain why the save was blocked",
        )
        checks.append("external-change-blocks-stale-json")

        window.reload()
        require(window.position.get_active_id() == "right", "final reload missed position")
        require(
            json.loads(window.buffer.get_text(*window.buffer.get_bounds(), True))
            == external,
            "final reload did not restore both panels",
        )
        checks.append("reload-restores-both-panels")
        window.opacity.set_value(60)
        window.apply_controls(None)
        require(legacy.read_text() == "right\n", "final GUI save lost legacy position")
        GLib.timeout_add(250, guarded(finish))
        return False

    def finish():
        subprocess.run(
            ["grim", str(output / "preferences.png")], check=True, timeout=5
        )
        evidence = {
            "status": "passed",
            "checks": checks,
            "final_config": read_config(),
            "legacy_position": legacy.read_text().strip(),
            "screenshots": ["conflict.png", "preferences.png"],
            "host_config_changes": 0,
        }
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        window.destroy()
        Gtk.main_quit()
        return False

    GLib.timeout_add(500, guarded(exercise_initial_conflict))
    Gtk.main()
    if failures:
        raise RuntimeError("decoration settings client failed") from failures[0]


def wait_for_compositor(compositor, runtime, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        sockets = list(runtime.glob("sway-ipc*.sock"))
        displays = [path for path in runtime.glob("wayland-*") if path.is_socket()]
        if sockets and displays:
            return sockets[0], displays[0].name
        if compositor.poll() is not None:
            raise RuntimeError(f"private compositor exited {compositor.returncode}")
        time.sleep(0.05)
    raise RuntimeError("timed out waiting for private compositor sockets")


def run_verifier(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="decoration-settings-") as directory:
        base = Path(directory)
        runtime = base / "run"
        runtime.mkdir(mode=0o700)
        config_home = base / "config"
        state_home = base / "state"
        config = config_home / "mbp-intel/decoration.json"
        legacy = state_home / "mbp-intel/decoration/position"
        config.parent.mkdir(parents=True)
        legacy.parent.mkdir(parents=True)
        initial = {"position": "bottom", "opacity": 0.78, "corner_radius": 7}
        config.write_text(json.dumps(initial) + "\n")
        legacy.write_text("bottom\n")
        sway_config = base / "sway.conf"
        sway_config.write_text(
            "xwayland disable\n"
            "output HEADLESS-1 mode 1440x900\n"
            "output * bg #13091f solid_color\n"
            "seat seat0 fallback true\n"
            'for_window [app_id="mbp-intel-decoration-settings"] '
            "floating enable, resize set 1000 620\n"
        )
        env = dict(
            os.environ,
            XDG_RUNTIME_DIR=str(runtime),
            XDG_CONFIG_HOME=str(config_home),
            XDG_STATE_HOME=str(state_home),
            WLR_BACKENDS="headless",
            WLR_HEADLESS_OUTPUTS="1",
            WLR_RENDERER="pixman",
            NO_AT_BRIDGE="1",
            GTK_USE_PORTAL="0",
        )
        for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
            env.pop(key, None)

        log_path = output / "runtime.log"
        with log_path.open("w") as log:
            compositor = subprocess.Popen(
                ["swayfx", "-c", str(sway_config)],
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                sway_socket, wayland_display = wait_for_compositor(
                    compositor, runtime
                )
                env["SWAYSOCK"] = str(sway_socket)
                env["WAYLAND_DISPLAY"] = wayland_display
                result = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--client",
                        "--source",
                        str(SOURCE),
                        "--config-home",
                        str(config_home),
                        "--state-home",
                        str(state_home),
                        "--output",
                        str(output),
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                    timeout=30,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"decoration settings client exited {result.returncode}"
                    )
                evidence_path = output / "evidence.json"
                if not evidence_path.is_file():
                    raise RuntimeError("client exited without successful evidence")
                evidence = json.loads(evidence_path.read_text())
                require(evidence.get("status") == "passed", "evidence did not pass")
                for name in evidence["screenshots"]:
                    require((output / name).is_file(), f"missing screenshot {name}")
            finally:
                if compositor.poll() is None:
                    os.killpg(compositor.pid, signal.SIGTERM)
                    try:
                        compositor.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(compositor.pid, signal.SIGKILL)
                        compositor.wait()
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--client", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--config-home", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--state-home", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.client:
        required = (args.source, args.config_home, args.state_home)
        if any(value is None for value in required):
            parser.error("internal client paths are required")
        run_client(args.source, args.config_home, args.state_home, args.output)
    else:
        run_verifier(args.output)


if __name__ == "__main__":
    main()
