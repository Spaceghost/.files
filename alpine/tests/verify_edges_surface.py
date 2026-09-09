#!/usr/bin/env python3
"""Check the BOTTOM-layer backdrop in a private native SwayFX session.

Plank 1 claims six things that only a compositor can settle: the surface is on
BOTTOM, it reserves nothing, it does not cover a Conky reading card, it passes
every click through, it draws the graduations from the theme's own palette, and
killing it puts the frame back exactly as it was. This runs a throwaway SwayFX
with a fixture card and a fixture bar and checks all six against real pixels.

Nothing here touches the live session: private HOME, XDG directories, D-Bus and
compositor throughout, and the screenshots are the evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shlex
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import traceback

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / "alpine/desktop/.local"
EDGES = DESKTOP / "bin/oldbook-edges"
SPACE = DESKTOP / "bin/oldbook-space"
PRIVATE_BUS_MARKER = "OLDBOOK_EDGES_PRIVATE_BUS"
WIDTH, HEIGHT = 1440, 900
COLUMNS, ROWS = 72, 45
BAR_ZONE = 32
CARD = {"x": 600, "y": 480, "width": 300, "height": 140}
CARD_COLOR = (255, 0, 255)
BAR_COLOR = (0, 255, 255)
GROUND = (16, 16, 16)
TICK_ALPHA = 0.14
IPC_HEADER = struct.Struct("=6sII")
IPC_TYPES = {"get_outputs": 3, "get_tree": 4, "get_workspaces": 1}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class SwayIPC:
    def __init__(self, path):
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.settimeout(4)
        self.connection.connect(str(path))

    def read(self, size, deadline):
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("private compositor IPC response timed out")
            self.connection.settimeout(remaining)
            part = self.connection.recv(size - len(data))
            if not part:
                raise ConnectionError("private compositor IPC disconnected")
            data.extend(part)
        return data

    def request(self, kind, body=""):
        deadline = time.monotonic() + 4
        payload = body.encode()
        self.connection.settimeout(4)
        self.connection.sendall(IPC_HEADER.pack(b"i3-ipc", len(payload), kind) + payload)
        magic, size, returned = IPC_HEADER.unpack(self.read(IPC_HEADER.size, deadline))
        require(magic == b"i3-ipc" and returned == kind and size <= 32 * 1024 * 1024,
                "invalid private compositor IPC response")
        return json.loads(self.read(size, deadline))

    def close(self):
        self.connection.close()


def fixture_surface(namespace, layer, colour, geometry, zone):
    """A stand-in for a reading card or the bar, on the layer the real one uses."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, GtkLayerShell

    window = Gtk.Window()
    window.set_name("fixture")
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, namespace)
    GtkLayerShell.set_layer(window, getattr(GtkLayerShell.Layer, layer))
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, geometry["y"])
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.LEFT, geometry["x"])
    GtkLayerShell.set_exclusive_zone(window, zone)
    window.set_size_request(geometry["width"], geometry["height"])
    style = Gtk.CssProvider()
    style.load_from_data(f"#fixture {{ background: {colour}; }}".encode())
    Gtk.StyleContext.add_provider_for_screen(window.get_screen(), style,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)
    window.show_all()
    Gtk.main()


def build_pointer(base):
    source = REPO / "alpine/packages/waybar-art/tests"
    subprocess.run(["wayland-scanner", "client-header", str(source / "pointer.xml"),
                    str(base / "pointer.h")], check=True)
    subprocess.run(["wayland-scanner", "private-code", str(source / "pointer.xml"),
                    str(base / "pointer-protocol.c")], check=True)
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "wayland-client"], text=True))
    binary = base / "pointer-input"
    subprocess.run(["cc", "-std=c11", "-I", str(base), str(source / "pointer-input.c"),
                    str(base / "pointer-protocol.c"), "-o", str(binary), *flags], check=True)
    return binary


def pointer_reply(process, expected):
    deadline = time.monotonic() + 4
    reply = bytearray()
    while not reply.endswith(b"\n"):
        remaining = deadline - time.monotonic()
        require(remaining > 0 and select.select([process.stdout], [], [], remaining)[0],
                "private pointer reply timed out")
        part = os.read(process.stdout.fileno(), 1)
        require(part and len(reply) < 64, "private pointer disconnected or sent a bad reply")
        reply.extend(part)
    require(reply.decode().strip() == expected, "private pointer command failed")


def walk(node):
    yield node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        yield from walk(child)


class Frame:
    """One grim capture, read as pixels."""

    def __init__(self, path):
        import gi

        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf

        picture = GdkPixbuf.Pixbuf.new_from_file(str(path))
        self.pixels = picture.get_pixels()
        self.stride = picture.get_rowstride()
        self.channels = picture.get_n_channels()
        self.width, self.height = picture.get_width(), picture.get_height()
        self.digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def at(self, x, y):
        start = y * self.stride + x * self.channels
        return tuple(self.pixels[start:start + 3])


def near(first, second, tolerance=3):
    return all(abs(one - two) <= tolerance for one, two in zip(first, second))


def blend(ground, ink, alpha):
    return tuple(round(base * (1 - alpha) + value * alpha) for base, value in zip(ground, ink))


def palette_role(role):
    sys.path.insert(0, str(DESKTOP / "lib/oldbook"))
    import overlay_theme

    value = overlay_theme.read_palette()[role]
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def process_time(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def run_verifier(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    checks, states, screenshots = [], {}, []
    evidence = {
        "status": "running", "checks": checks, "states": states, "screenshots": screenshots,
        "isolation": "private D-Bus, HOME, XDG directories, headless compositor",
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    sources = [EDGES, SPACE, DESKTOP / "share/oldbook/qml/SignalMargin.qml",
               *(DESKTOP / "lib/oldbook" / name for name in
                 ("desktop_space.py", "edges_surface.py", "overlay_theme.py")),
               DESKTOP / "lib/oldbook/native/layer_shell_bridge.cpp"]
    evidence["source_sha256"] = {str(path.relative_to(REPO)):
                                 hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sources}

    def write_evidence():
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")

    ink = palette_role("muted")
    evidence["palette_muted"] = "#%02x%02x%02x" % ink
    expected_tick = blend(GROUND, ink, TICK_ALPHA)
    evidence["expected_tick"] = "#%02x%02x%02x" % expected_tick
    require(max(abs(one - two) for one, two in zip(expected_tick, GROUND)) >= 6,
            "the theme's muted role is too close to the test ground to see a tick")

    with tempfile.TemporaryDirectory(prefix="edges-surface-") as directory:
        base = Path(directory)
        runtime = base / "run"
        runtime.mkdir(mode=0o700)
        home, config_home, state_home, cache_home, data_home = (
            base / name for name in ("home", "config", "state", "cache", "data"))
        for path in (home, config_home, state_home, cache_home, data_home):
            path.mkdir()
        (config_home / "oldbook").mkdir()
        (config_home / "oldbook/edges.json").write_text(
            json.dumps({"enabled": True, "signal-margin": True}) + "\n")
        sway_config = output / "sway.conf"
        sway_config.write_text(
            "xwayland disable\n"
            f"output HEADLESS-1 mode {WIDTH}x{HEIGHT}\n"
            "output HEADLESS-1 position 0 0\n"
            f"output * bg #{'%02x%02x%02x' % GROUND} solid_color\n"
            "seat seat0 fallback true\n"
            "focus_follows_mouse yes\n"
            "default_border pixel 0\n"
            "default_floating_border pixel 0\n"
            "corner_radius 0\n"
            "blur disable\n"
            "shadows disable\n"
            "default_dim_inactive 0.0\n"
            'layer_effects "oldbook-edges" {\n'
            "    blur disable\n    shadows disable\n    corner_radius 0\n}\n"
            'for_window [app_id="edges-window"] floating enable, '
            "resize set 520 300, move absolute position 120 140\n")
        env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime),
                   XDG_CONFIG_HOME=str(config_home), XDG_STATE_HOME=str(state_home),
                   XDG_CACHE_HOME=str(cache_home), XDG_DATA_HOME=str(data_home),
                   WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1", WLR_RENDERER="pixman",
                   # A deterministic frame: the output mask is a compositor patch
                   # with its own contract and its arc would round every capture.
                   SPACEGHOST_SCREEN_CORNER_RADIUS="0",
                   QT_QPA_PLATFORM="wayland", QT_QUICK_BACKEND="software",
                   NO_AT_BRIDGE="1", GTK_USE_PORTAL="0")
        for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY"):
            env.pop(key, None)
        # Build the bridge once against the real cache so the private run does
        # not pay for a compile it is not testing.
        env["OLDBOOK_LAYER_SHELL_LIBRARY"] = subprocess.check_output(
            [sys.executable, str(REPO / "alpine/bin/build-layer-shell-bridge")],
            text=True).strip()
        evidence["layer_shell_library"] = env["OLDBOOK_LAYER_SHELL_LIBRARY"]

        processes = []
        expected_exits = set()
        connection = None
        pointer_binary = build_pointer(base)
        with (output / "runtime.log").open("w") as log:

            def spawn(name, command, pointer=False):
                process = subprocess.Popen(
                    command, env=env, stdout=subprocess.PIPE if pointer else log,
                    stdin=subprocess.PIPE if pointer else subprocess.DEVNULL,
                    stderr=log, text=True, start_new_session=True)
                processes.append((name, process))
                return process

            def ipc(kind="get_tree"):
                return connection.request(IPC_TYPES[kind])

            def wait_for(test, message, seconds=20, interval=0.05):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    for name, process in processes:
                        if (process.poll() is not None and name != "pointer"
                                and name not in expected_exits):
                            raise RuntimeError(f"{name} exited {process.returncode}")
                    result = test()
                    if result:
                        return result
                    time.sleep(interval)
                raise AssertionError(message)

            def surfaces(namespace):
                return [item for node in ipc("get_outputs")
                        for item in node.get("layer_shell_surfaces", [])
                        if item["namespace"] == namespace]

            def usable():
                return next(item["rect"] for item in ipc("get_workspaces")
                            if item.get("visible"))

            def capture(name):
                time.sleep(0.6)
                path = output / (name + ".png")
                subprocess.run(["grim", "-o", "HEADLESS-1", str(path)],
                               env=env, check=True, timeout=10)
                screenshots.append(path.name)
                return Frame(path)

            def record(name, state=None):
                checks.append(name)
                if state is not None:
                    states[name] = state
                write_evidence()

            try:
                spawn("swayfx", ["swayfx", "-c", str(sway_config)])

                def ready():
                    sockets = list(runtime.glob("sway-ipc*.sock"))
                    displays = [p for p in runtime.glob("wayland-*") if p.is_socket()]
                    return (sockets[0], displays[0].name) if sockets and displays else None

                sway_socket, wayland_display = wait_for(ready, "private compositor not ready")
                env["SWAYSOCK"] = str(sway_socket)
                env["WAYLAND_DISPLAY"] = wayland_display
                connection = SwayIPC(sway_socket)

                spawn("fixture-card", [sys.executable, str(Path(__file__).resolve()),
                                       "--fixture", "card"])
                spawn("fixture-bar", [sys.executable, str(Path(__file__).resolve()),
                                      "--fixture", "bar"])
                wait_for(lambda: surfaces("conky") and surfaces("top"),
                         "fixture card and bar did not appear")
                spawn("window", ["foot", "--app-id", "edges-window", "--title", "Edges window",
                                 "sh", "-c", "printf 'private window\\n'; sleep 600"])
                wait_for(lambda: next((item for item in walk(ipc())
                                       if item.get("app_id") == "edges-window"), None),
                         "private window did not appear")
                card = surfaces("conky")[0]["extent"]
                before_usable = usable()
                baseline = capture("00-before")
                require(near(baseline.at(CARD["x"] + 4, CARD["y"] + 4), CARD_COLOR),
                        "the fixture card is not where the test placed it")

                # -- plank 0 -------------------------------------------------
                surface = spawn("edges", [sys.executable, str(EDGES), "run"])
                space = wait_for(
                    lambda: json.loads((runtime / "oldbook/space.json").read_text())
                    if (runtime / "oldbook/space.json").is_file() else None,
                    "oldbook-space published no region")
                region = next(item for item in space["regions"]
                              if item["output"] == "HEADLESS-1")
                names = [item["name"] for item in region["occupied"]]
                require(names.count("conky") == 1 and "top" in names and "edges-window" in names,
                        f"the region did not name the card, the bar and the window: {names}")
                require("oldbook-edges" not in names, "the effect reserved itself")
                cell_width, cell_height = WIDTH / COLUMNS, HEIGHT / ROWS
                for corner_x, corner_y in ((CARD["x"] + 2, CARD["y"] + 2),
                                           (CARD["x"] + CARD["width"] - 2,
                                            CARD["y"] + CARD["height"] - 2)):
                    mark = region["grid"][int(corner_y // cell_height)][int(corner_x // cell_width)]
                    require(mark == "#", "a Conky cell was published as free")
                record("space-excludes-conky",
                       {"occupied": region["occupied"], "free_cells": region["free_cells"]})

                # -- the surface ---------------------------------------------
                # A surface is listed as soon as it is created and reports a
                # zero extent until it has committed its first buffer.
                mapped = wait_for(
                    lambda: next((item for item in surfaces("oldbook-edges")
                                  if item["extent"]["width"] > 0), None),
                    "the backdrop never committed a frame")
                require(len(surfaces("oldbook-edges")) == 1,
                        f"expected one backdrop surface, got {len(surfaces('oldbook-edges'))}")
                require(mapped["layer"] == "bottom",
                        f"the backdrop is on {mapped['layer']}, not bottom")
                require(mapped["extent"] == {"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
                        f"the backdrop is not the whole output: {mapped['extent']}")
                record("bottom-layer-full-output", {"surface": mapped})

                after_usable = usable()
                require(after_usable == before_usable,
                        f"the backdrop reserved space: {before_usable} -> {after_usable}")
                record("zero-exclusive-zone", {"usable": after_usable})

                require(surfaces("conky")[0]["extent"] == card,
                        "the reading card moved when the backdrop appeared")
                record("conky-did-not-reflow", {"card": card})

                # -- the pixels ----------------------------------------------
                drawn = capture("01-drawn")
                covered = [(x, y) for y in range(CARD["y"], CARD["y"] + CARD["height"])
                           for x in range(CARD["x"], CARD["x"] + CARD["width"])
                           if not near(drawn.at(x, y), CARD_COLOR)]
                require(not covered,
                        f"{len(covered)} pixels of the reading card were painted over, "
                        f"first at {covered[0] if covered else None}")
                record("cards-not-covered", {"card_pixels_checked":
                                             CARD["width"] * CARD["height"]})

                ticks, strays = 0, []
                for y in range(HEIGHT):
                    row = region["grid"][min(ROWS - 1, int(y // cell_height))]
                    for x in range(WIDTH):
                        if row[min(COLUMNS - 1, int(x // cell_width))] != ".":
                            continue
                        pixel = drawn.at(x, y)
                        if near(pixel, GROUND, 1):
                            continue
                        if near(pixel, expected_tick):
                            ticks += 1
                        else:
                            strays.append((x, y, pixel))
                require(not strays, f"{len(strays)} free-space pixels are not the palette's "
                                    f"graduation colour, first {strays[0] if strays else None}")
                require(ticks >= 200, f"only {ticks} graduation pixels were drawn")
                record("graduations-from-the-palette",
                       {"tick_pixels": ticks, "colour": evidence["expected_tick"]})

                # -- input ----------------------------------------------------
                pointer = spawn("pointer", [str(pointer_binary)], pointer=True)
                require(pointer.stdout.readline().strip() == "ready", "pointer fixture failed")

                def move(x, y):
                    pointer.stdin.write(f"move {round(x * 800 / WIDTH)} "
                                        f"{round(y * 600 / HEIGHT)}\n")
                    pointer.stdin.flush()
                    pointer_reply(pointer, "ok")

                window = next(item for item in walk(ipc()) if item.get("app_id") == "edges-window")
                move(window["rect"]["x"] + window["rect"]["width"] // 2,
                     window["rect"]["y"] + window["rect"]["height"] // 2)
                focused = wait_for(
                    lambda: next((item for item in walk(ipc())
                                  if item.get("app_id") == "edges-window" and item.get("focused")),
                                 None),
                    "the pointer did not reach the window under the backdrop", seconds=6)
                record("input-passes-through", {"focused": focused["app_id"]})

                # -- nothing moves at rest -----------------------------------
                started = process_time(surface.pid)
                time.sleep(3)
                idle_ticks = process_time(surface.pid) - started
                require(idle_ticks <= 5,
                        f"the backdrop burned {idle_ticks} clock ticks doing nothing")
                still = capture("02-still")
                require(still.digest == drawn.digest,
                        "the frame changed with nothing happening")
                record("static-at-rest", {"idle_clock_ticks": idle_ticks})

                # -- revert ---------------------------------------------------
                expected_exits.add("edges")
                surface.send_signal(signal.SIGTERM)
                surface.wait(timeout=15)
                wait_for(lambda: not surfaces("oldbook-edges"), "the backdrop did not unmap")
                wait_for(lambda: not (runtime / "oldbook/space.json").exists(),
                         "the region record outlived its only consumer")
                restored = capture("03-after")
                require(restored.digest == baseline.digest,
                        "the desktop did not return to the frame it started from")
                require(surfaces("conky")[0]["extent"] == card, "the card moved on the way out")
                require(usable() == before_usable, "the usable area changed on the way out")
                record("revertible", {"frame_sha256": restored.digest})

                evidence["status"] = "passed"
            except Exception:
                evidence["status"] = "failed"
                evidence["error"] = traceback.format_exc()
                raise
            finally:
                if connection is not None:
                    connection.close()
                for _name, process in reversed(processes):
                    if process.poll() is None:
                        try:
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        except OSError:
                            process.terminate()
                for _name, process in processes:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                write_evidence()
    return 0


def enter_private_bus():
    if os.environ.get(PRIVATE_BUS_MARKER):
        return
    env = dict(os.environ, **{PRIVATE_BUS_MARKER: "1"})
    os.execvpe("dbus-run-session", ["dbus-run-session", "--", sys.executable,
                                    str(Path(__file__).resolve()), *sys.argv[1:]], env)


FIXTURES = {"card": ("conky", "BACKGROUND", "#ff00ff", CARD, 0),
            "bar": ("top", "OVERLAY", "#00ffff",
                    {"x": 0, "y": 0, "width": WIDTH, "height": BAR_ZONE}, BAR_ZONE)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixture", choices=sorted(FIXTURES), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.fixture:
        fixture_surface(*FIXTURES[args.fixture])
        return
    if args.output is None:
        parser.error("--output is required")
    enter_private_bus()
    run_verifier(args.output)


if __name__ == "__main__":
    main()
