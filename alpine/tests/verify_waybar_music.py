#!/usr/bin/env python3
"""Exercise Waybar MPRIS selection and controls in a private desktop session."""

import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[2]
WAYBAR_CONFIG = REPO / "alpine/desktop/.config/waybar/config.jsonc"
WAYBAR_STYLE = REPO / "alpine/desktop/.config/waybar/style.css"
POINTER_SOURCE = REPO / "alpine/packages/waybar-art/tests/pointer-input.c"
POINTER_PROTOCOL = REPO / "alpine/packages/waybar-art/tests/pointer.xml"
PRIVATE_BUS_MARKER = "OLDBOOK_WAYBAR_MUSIC_PRIVATE_BUS"
EXPECTED_TITLE = "Selected Coast to Coast"
EXPECTED_ACTIONS = [
    "GhostPlanet:Previous",
    "GhostPlanet:PlayPause",
    "GhostPlanet:Next",
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_fake_mpris(actions, player_name, track_title):
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    introspection = """<node>
<interface name="org.mpris.MediaPlayer2">
 <method name="Raise"/><method name="Quit"/>
 <property name="CanQuit" type="b" access="read"/>
 <property name="CanRaise" type="b" access="read"/>
 <property name="HasTrackList" type="b" access="read"/>
 <property name="Identity" type="s" access="read"/>
 <property name="DesktopEntry" type="s" access="read"/>
 <property name="SupportedUriSchemes" type="as" access="read"/>
 <property name="SupportedMimeTypes" type="as" access="read"/>
</interface>
<interface name="org.mpris.MediaPlayer2.Player">
 <method name="Next"/><method name="Previous"/><method name="Pause"/>
 <method name="PlayPause"/><method name="Stop"/><method name="Play"/>
 <method name="Seek"><arg direction="in" type="x"/></method>
 <method name="SetPosition"><arg direction="in" type="o"/><arg direction="in" type="x"/></method>
 <method name="OpenUri"><arg direction="in" type="s"/></method>
 <property name="PlaybackStatus" type="s" access="read"/>
 <property name="LoopStatus" type="s" access="readwrite"/>
 <property name="Rate" type="d" access="readwrite"/>
 <property name="Shuffle" type="b" access="readwrite"/>
 <property name="Metadata" type="a{sv}" access="read"/>
 <property name="Volume" type="d" access="readwrite"/>
 <property name="Position" type="x" access="read"/>
 <property name="MinimumRate" type="d" access="read"/>
 <property name="MaximumRate" type="d" access="read"/>
 <property name="CanGoNext" type="b" access="read"/>
 <property name="CanGoPrevious" type="b" access="read"/>
 <property name="CanPlay" type="b" access="read"/>
 <property name="CanPause" type="b" access="read"/>
 <property name="CanSeek" type="b" access="read"/>
 <property name="CanControl" type="b" access="read"/>
</interface></node>"""
    node = Gio.DBusNodeInfo.new_for_xml(introspection)
    connection = Gio.bus_get_sync(Gio.BusType.SESSION)

    def method_call(
        _connection, _sender, _path, _interface, method, _parameters, invocation
    ):
        with actions.open("a") as stream:
            stream.write(f"{player_name}:{method}\n")
        invocation.return_value(None)

    def get_property(_connection, _sender, _path, interface, name):
        if interface == "org.mpris.MediaPlayer2":
            values = {
                "CanQuit": GLib.Variant("b", False),
                "CanRaise": GLib.Variant("b", False),
                "HasTrackList": GLib.Variant("b", False),
                "Identity": GLib.Variant("s", f"{player_name} Radio"),
                "DesktopEntry": GLib.Variant("s", "oldbook-test"),
                "SupportedUriSchemes": GLib.Variant("as", []),
                "SupportedMimeTypes": GLib.Variant("as", []),
            }
        else:
            metadata = {
                "mpris:trackid": GLib.Variant("o", "/org/oldbook/TestTrack"),
                "mpris:length": GLib.Variant("x", 245000000),
                "xesam:title": GLib.Variant("s", track_title),
                "xesam:artist": GLib.Variant(
                    "as", ["Zorak and the Brak Pack"]
                ),
                "xesam:album": GLib.Variant("s", "Safe Test Broadcast"),
            }
            values = {
                "PlaybackStatus": GLib.Variant("s", "Playing"),
                "LoopStatus": GLib.Variant("s", "None"),
                "Rate": GLib.Variant("d", 1.0),
                "Shuffle": GLib.Variant("b", False),
                "Metadata": GLib.Variant("a{sv}", metadata),
                "Volume": GLib.Variant("d", 0.7),
                "Position": GLib.Variant("x", 42000000),
                "MinimumRate": GLib.Variant("d", 1.0),
                "MaximumRate": GLib.Variant("d", 1.0),
                "CanGoNext": GLib.Variant("b", True),
                "CanGoPrevious": GLib.Variant("b", True),
                "CanPlay": GLib.Variant("b", True),
                "CanPause": GLib.Variant("b", True),
                "CanSeek": GLib.Variant("b", True),
                "CanControl": GLib.Variant("b", True),
            }
        return values[name]

    for interface in node.interfaces:
        connection.register_object(
            "/org/mpris/MediaPlayer2",
            interface,
            method_call,
            get_property,
            None,
        )
    Gio.bus_own_name_on_connection(
        connection,
        f"org.mpris.MediaPlayer2.{player_name}",
        Gio.BusNameOwnerFlags.NONE,
        None,
        None,
    )
    print("ready", flush=True)
    GLib.MainLoop().run()


def wait_for(test, processes, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for name, process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited {process.returncode}")
        value = test()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError("timed out waiting for private desktop state")


def build_pointer(base):
    header = base / "pointer.h"
    protocol_code = base / "pointer-protocol.c"
    executable = base / "pointer-input"
    subprocess.run(
        ["wayland-scanner", "client-header", str(POINTER_PROTOCOL), str(header)],
        check=True,
    )
    subprocess.run(
        [
            "wayland-scanner",
            "private-code",
            str(POINTER_PROTOCOL),
            str(protocol_code),
        ],
        check=True,
    )
    flags = shlex.split(
        subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "wayland-client"], text=True
        )
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-I",
            str(base),
            str(POINTER_SOURCE),
            str(protocol_code),
            "-o",
            str(executable),
            *flags,
        ],
        check=True,
    )
    return executable


def run_verifier(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="waybar-music-") as directory:
        base = Path(directory)
        runtime = base / "run"
        runtime.mkdir(mode=0o700)
        config_home = base / "config"
        state_home = base / "state"
        cache_home = base / "cache"
        for path in (config_home, state_home, cache_home):
            path.mkdir()
        actions = output / "actions"
        pointer_executable = build_pointer(base)

        config = json.loads(WAYBAR_CONFIG.read_text())
        top = config[0]
        top["output"] = "HEADLESS-1"
        top["fixed-center"] = True
        top["modules-left"] = []
        top["modules-right"] = []
        bar_config = output / "waybar.json"
        bar_config.write_text(json.dumps([top]) + "\n")
        style = output / "style.css"
        style.write_text(WAYBAR_STYLE.read_text())
        (output / "waybar-state.css").write_text("")
        sway_config = output / "sway.conf"
        sway_config.write_text(
            "xwayland disable\n"
            "output HEADLESS-1 mode 1440x900\n"
            "output HEADLESS-1 bg #130a20 solid_color\n"
            "seat seat0 fallback true\n"
        )

        env = dict(
            os.environ,
            HOME=str(base / "home"),
            XDG_RUNTIME_DIR=str(runtime),
            XDG_CONFIG_HOME=str(config_home),
            XDG_STATE_HOME=str(state_home),
            XDG_CACHE_HOME=str(cache_home),
            WLR_BACKENDS="headless",
            WLR_HEADLESS_OUTPUTS="1",
            WLR_RENDERER="pixman",
            NO_AT_BRIDGE="1",
            GTK_USE_PORTAL="0",
        )
        for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY"):
            env.pop(key, None)

        processes = []
        log_path = output / "runtime.log"
        with log_path.open("w") as log:

            def spawn(name, command, stdout=None):
                process = subprocess.Popen(
                    command,
                    env=env,
                    stdin=subprocess.PIPE if name == "pointer" else None,
                    stdout=stdout if stdout is not None else log,
                    stderr=log,
                    start_new_session=True,
                    text=True,
                )
                processes.append((name, process))
                return process

            try:
                compositor = spawn("swayfx", ["swayfx", "-c", str(sway_config)])

                def compositor_ready():
                    sockets = list(runtime.glob("sway-ipc*.sock"))
                    displays = [
                        path for path in runtime.glob("wayland-*") if path.is_socket()
                    ]
                    return (sockets[0], displays[0].name) if sockets and displays else None

                sway_socket, wayland_display = wait_for(
                    compositor_ready, [("swayfx", compositor)]
                )
                env["SWAYSOCK"] = str(sway_socket)
                env["WAYLAND_DISPLAY"] = wayland_display

                playerctld = spawn("playerctld", ["playerctld", "daemon"])
                service_a = spawn(
                    "MoonbaseOne",
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--fake-mpris",
                        str(actions),
                        "MoonbaseOne",
                        "Older Test Transmission",
                    ],
                    stdout=subprocess.PIPE,
                )
                require(
                    service_a.stdout.readline().strip() == "ready",
                    "first MPRIS service failed",
                )
                service_b = spawn(
                    "GhostPlanet",
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--fake-mpris",
                        str(actions),
                        "GhostPlanet",
                        EXPECTED_TITLE,
                    ],
                    stdout=subprocess.PIPE,
                )
                require(
                    service_b.stdout.readline().strip() == "ready",
                    "second MPRIS service failed",
                )
                time.sleep(0.3)
                selected = subprocess.check_output(
                    ["playerctl", "--player=playerctld", "metadata", "title"],
                    env=env,
                    text=True,
                    timeout=5,
                ).strip()
                require(selected == EXPECTED_TITLE, f"selected {selected!r}")

                bar = spawn(
                    "waybar",
                    ["waybar", "-c", str(bar_config), "-s", str(style)],
                )
                wait_for(
                    lambda: "Bar configured" in log_path.read_text(),
                    [("swayfx", compositor), ("waybar", bar)],
                )
                time.sleep(1)
                subprocess.run(
                    ["grim", str(output / "music.png")],
                    env=env,
                    check=True,
                    timeout=5,
                )

                pointer = spawn(
                    "pointer",
                    [str(pointer_executable)],
                    stdout=subprocess.PIPE,
                )
                require(
                    pointer.stdout.readline().strip() == "ready",
                    "virtual pointer failed",
                )

                def event(command):
                    pointer.stdin.write(command + "\n")
                    pointer.stdin.flush()
                    require(
                        pointer.stdout.readline().strip() == "ok",
                        "virtual pointer stopped",
                    )

                for x in (560, 720, 885):
                    event(f"move {round(x * 800 / 1440)} 16")
                    event("press 272")
                    event("release 272")
                    time.sleep(0.25)
                event("move 400 16")
                time.sleep(1.2)
                subprocess.run(
                    ["grim", str(output / "tooltip.png")],
                    env=env,
                    check=True,
                    timeout=5,
                )
                found = actions.read_text().splitlines() if actions.exists() else []
                require(found == EXPECTED_ACTIONS, f"MPRIS actions were {found!r}")
                evidence = {
                    "selected": selected,
                    "actions": found,
                    "screenshots": ["music.png", "tooltip.png"],
                }
                (output / "evidence.json").write_text(
                    json.dumps(evidence, indent=2) + "\n"
                )
            finally:
                for _name, process in reversed(processes):
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
    print(output)


def enter_private_bus():
    if os.environ.get(PRIVATE_BUS_MARKER) == "1":
        require("DBUS_SESSION_BUS_ADDRESS" in os.environ, "private D-Bus is missing")
        return
    env = dict(os.environ)
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    env[PRIVATE_BUS_MARKER] = "1"
    os.execvpe(
        "dbus-run-session",
        ["dbus-run-session", "--", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        env,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fake-mpris", nargs=3, metavar=("ACTIONS", "PLAYER", "TITLE"))
    args = parser.parse_args()
    if args.fake_mpris:
        run_fake_mpris(Path(args.fake_mpris[0]), *args.fake_mpris[1:])
        return
    if args.output is None:
        parser.error("--output is required")
    enter_private_bus()
    run_verifier(args.output)


if __name__ == "__main__":
    main()
