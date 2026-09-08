#!/usr/bin/env python3
"""Check floating-caption attachment in a private native SwayFX session."""

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
HELPER = REPO / "alpine/desktop/.local/bin/mbp-intel-decoration"
PRIVATE_BUS_MARKER = "MBP_INTEL_DECORATION_ATTACHMENT_PRIVATE_BUS"
WIDTH = 1440
HEIGHT = 900
TOP_ZONE = 32
IPC_HEADER = struct.Struct("=6sII")
IPC_TYPES = {"get_workspaces": 1, "get_outputs": 3, "get_tree": 4}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class SwayIPC:
    """Keep geometry sampling within a frame instead of spawning swaymsg."""

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

    def requests(self, requests):
        deadline = time.monotonic() + 4
        encoded = [(kind, value.encode()) for kind, value in requests]
        self.connection.settimeout(4)
        self.connection.sendall(b"".join(
            IPC_HEADER.pack(b"i3-ipc", len(body), kind) + body
            for kind, body in encoded
        ))
        replies = []
        for kind, _body in encoded:
            magic, size, returned = IPC_HEADER.unpack(self.read(IPC_HEADER.size, deadline))
            require(magic == b"i3-ipc" and returned == kind and size <= 32 * 1024 * 1024,
                    "invalid private compositor IPC response")
            replies.append(json.loads(self.read(size, deadline)))
        return replies

    def close(self):
        self.connection.close()


def pointer_reply(process, expected):
    deadline = time.monotonic() + 4
    reply = bytearray()
    while not reply.endswith(b"\n"):
        remaining = deadline - time.monotonic()
        require(remaining > 0 and select.select([process.stdout], [], [], remaining)[0],
                "private pointer reply timed out")
        part = os.read(process.stdout.fileno(), 1)
        require(part and len(reply) < 64, "private pointer disconnected or sent invalid reply")
        reply.extend(part)
    require(reply.decode().strip() == expected, "private pointer command failed")


def fixture_panel():
    """Reserve the same top space as the desktop bar, without host modules."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gtk, GtkLayerShell

    window = Gtk.Window()
    window.set_name("attachment-fixture-top")
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "attachment-fixture-top")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)
    for edge in ("TOP", "LEFT", "RIGHT"):
        GtkLayerShell.set_anchor(window, getattr(GtkLayerShell.Edge, edge), True)
    GtkLayerShell.set_exclusive_zone(window, TOP_ZONE)
    window.set_size_request(-1, TOP_ZONE)
    label = Gtk.Label(label="PRIVATE DECORATION ATTACHMENT PREVIEW")
    window.add(label)
    style = Gtk.CssProvider()
    style.load_from_data(
        b"#attachment-fixture-top { background: #21142d; color: #dca7ff; "
        b"border: none; padding: 0; }"
    )
    Gtk.StyleContext.add_provider_for_screen(
        window.get_screen(), style, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )
    window.show_all()
    Gtk.main()


def build_pointer(base):
    source = REPO / "alpine/packages/waybar-art/tests"
    subprocess.run(
        ["wayland-scanner", "client-header", str(source / "pointer.xml"),
         str(base / "pointer.h")], check=True
    )
    subprocess.run(
        ["wayland-scanner", "private-code", str(source / "pointer.xml"),
         str(base / "pointer-protocol.c")], check=True
    )
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "wayland-client"], text=True
    ))
    binary = base / "pointer-input"
    subprocess.run(
        ["cc", "-std=c11", "-I", str(base), str(source / "pointer-input.c"),
         str(base / "pointer-protocol.c"), "-o", str(binary), *flags], check=True
    )
    return binary


def walk(node):
    yield node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        yield from walk(child)


def bottom_corner_pixels(image_path, rect):
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    picture = GdkPixbuf.Pixbuf.new_from_file(str(image_path))
    pixels = picture.get_pixels()
    stride, channels = picture.get_rowstride(), picture.get_n_channels()

    def pixel(x, y):
        start = y * stride + x * channels
        return tuple(pixels[start:start + 3])

    x, y = rect["x"], rect["y"] + rect["height"] - 1
    width = rect["width"]
    return {"left_corner": pixel(x, y), "left_inset": pixel(x + 9, y),
            "right_corner": pixel(x + width - 1, y),
            "right_inset": pixel(x + width - 10, y)}


def run_verifier(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    checks = []
    states = {}
    screenshots = []
    evidence = {
        "status": "running",
        "checks": checks,
        "states": states,
        "screenshots": screenshots,
        "isolation": "private D-Bus, HOME, XDG directories, headless compositor",
        "host_config_changes": 0,
    }
    sources = [HELPER, *(REPO / "alpine/desktop/.local/lib/mbp_intel" / name
                        for name in ("decoration.py", "decoration_actions.py",
                                     "decoration_placement.py", "decoration_motion.py",
                                     "decoration_watch.py", "overlay_theme.py"))]

    def source_hashes():
        return {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sources}

    evidence["source_sha256"] = source_hashes()

    def write_evidence():
        (output / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )

    with tempfile.TemporaryDirectory(prefix="decoration-attachment-") as directory:
        base = Path(directory)
        runtime = base / "run"
        runtime.mkdir(mode=0o700)
        config_home = base / "config"
        state_home = base / "state"
        cache_home = base / "cache"
        home = base / "home"
        for path in (config_home, state_home, cache_home, home):
            path.mkdir()
        (config_home / "foot").mkdir()
        foot_config = config_home / "foot/foot.ini"
        foot_config.write_text(
            "[main]\nfont=monospace:size=11\npad=12x12\nresize-by-cells=no\n"
            "[colors-dark]\nbackground=33445b\nforeground=f3eaff\nalpha=1.0\n"
        )
        (config_home / "mbp-intel").mkdir()
        preferences = config_home / "mbp-intel/decoration.json"
        preferences.write_text(json.dumps({
            "position": "bottom", "opacity": 0.78, "corner_radius": 7
        }) + "\n")
        sway_config = output / "sway.conf"
        sway_config.write_text(
            "xwayland disable\n"
            f"output HEADLESS-1 mode {WIDTH}x{HEIGHT}\n"
            "output HEADLESS-1 position 0 0\n"
            "output * bg #13091f solid_color\n"
            "seat seat0 fallback true\n"
            "focus_follows_mouse no\n"
            "floating_modifier Mod4\n"
            "default_border pixel 0\n"
            "default_floating_border pixel 0\n"
            "corner_radius 7\n"
            "smart_corner_radius enable\n"
            'layer_effects "mbp-intel-decoration" {\n    corner_radius 0\n}\n'
            'for_window [app_id="attachment-floating"] floating enable, '
            "resize set 620 360, move absolute position 200 160\n"
            'for_window [app_id="attachment-hover"] floating enable, '
            "resize set 420 280, move absolute position 900 120\n"
        )
        env = dict(
            os.environ,
            HOME=str(home),
            XDG_RUNTIME_DIR=str(runtime),
            XDG_CONFIG_HOME=str(config_home),
            XDG_STATE_HOME=str(state_home),
            XDG_CACHE_HOME=str(cache_home),
            XDG_DATA_HOME=str(base / "data"),
            WLR_BACKENDS="headless",
            WLR_HEADLESS_OUTPUTS="1",
            WLR_RENDERER="pixman",
            NO_AT_BRIDGE="1",
            GTK_USE_PORTAL="0",
        )
        for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY"):
            env.pop(key, None)
        processes = []
        expected_exits = set()
        connection = None
        pointer_binary = build_pointer(base)
        with (output / "runtime.log").open("w") as log:

            def spawn(name, command, pointer=False):
                process = subprocess.Popen(
                    command, env=env, stdout=subprocess.PIPE if pointer else log,
                    stdin=subprocess.PIPE if pointer else subprocess.DEVNULL,
                    stderr=log, text=True, start_new_session=True
                )
                processes.append((name, process))
                return process

            def ipc(kind="get_tree", command=None):
                result = connection.requests([
                    (IPC_TYPES[kind], "") if command is None else (0, command)
                ])[0]
                if command is not None:
                    require(all(item.get("success") for item in result),
                            f"IPC command failed: {command}: {result!r}")
                return result

            def wait_for(test, message, seconds=8, interval=0.05):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    for name, process in processes:
                        if process.poll() is not None and name not in expected_exits:
                            raise RuntimeError(f"{name} exited {process.returncode}")
                    result = test()
                    if result:
                        return result
                    time.sleep(interval)
                raise AssertionError(message)

            def node(app_id):
                return next((item for item in walk(ipc())
                             if item.get("app_id") == app_id), None)

            def snapshot():
                tree, outputs, workspaces = connection.requests([
                    (IPC_TYPES[kind], "")
                    for kind in ("get_tree", "get_outputs", "get_workspaces")
                ])
                active = next(item for item in outputs if item["name"] == "HEADLESS-1")
                captions = [item for item in active.get("layer_shell_surfaces", [])
                            if item["namespace"] == "mbp-intel-decoration"]
                clients = {item["app_id"]: {key: item.get(key) for key in (
                    "id", "rect", "focused", "fullscreen_mode", "floating")}
                    for item in walk(tree) if item.get("app_id")}
                caption = captions[0] if len(captions) == 1 else None
                absolute = None
                if caption:
                    absolute = dict(caption["extent"])
                    absolute["x"] += active["rect"]["x"]
                    absolute["y"] += active["rect"]["y"]
                return {
                    "output": active["rect"], "captions": captions,
                    "caption_global_rect": absolute, "clients": clients,
                    "workspaces": workspaces,
                }

            def attached(state, edge, app_id="attachment-floating"):
                if len(state["captions"]) != 1 or app_id not in state["clients"]:
                    return False
                caption = state["captions"][0]
                actual = state["caption_global_rect"]
                client = state["clients"][app_id]["rect"]
                output_rect = state["output"]
                expected_tiled = {
                    "x": output_rect["x"],
                    "y": output_rect["y"] + TOP_ZONE,
                    "width": output_rect["width"],
                    "height": output_rect["height"] - TOP_ZONE,
                }
                geometry = (
                    actual["x"] == client["x"]
                    and actual["y"] == client["y"] + client["height"]
                    and actual["width"] == client["width"]
                    and 0 < actual["height"] < 80
                ) if edge == "bottom" else (
                    actual["x"] == client["x"] + client["width"]
                    and actual["y"] == client["y"]
                    and actual["height"] == client["height"]
                    and 0 < actual["width"] < 80
                )
                return (geometry and caption.get("exclusive_zone", -1) <= 0
                        and caption["layer"] == "top"
                        and state["clients"]["attachment-tiled"]["rect"] == expected_tiled)

            def workspace_edge(state, edge):
                if len(state["captions"]) != 1:
                    return False
                caption = state["captions"][0]
                actual = caption["extent"]
                geometry = (
                    actual["x"] == 5
                    and actual["y"] + actual["height"] == HEIGHT - 5
                    and actual["width"] == WIDTH - 10
                ) if edge == "bottom" else (
                    actual["x"] + actual["width"] == WIDTH - 5
                    and actual["y"] == TOP_ZONE + 5
                    and actual["height"] == HEIGHT - TOP_ZONE - 10
                )
                return (geometry and caption.get("exclusive_zone", 1) > 0
                        and caption["layer"] == "overlay")

            def capture(name, predicate, message):
                latest = {}

                def ready():
                    nonlocal latest
                    latest = snapshot()
                    return latest if predicate(latest) else None

                try:
                    state = wait_for(ready, message)
                except BaseException:
                    states[name + "-failed"] = latest
                    write_evidence()
                    raise
                # A second compositor/daemon cycle catches duplicate or stale surfaces.
                time.sleep(0.85)
                state = snapshot()
                require(predicate(state), message + " (unstable after settling)")
                states[name] = state
                screenshot = name + ".png"
                subprocess.run(["grim", "-o", "HEADLESS-1", str(output / screenshot)],
                               env=env, check=True, timeout=5)
                screenshots.append(screenshot)
                checks.append(name)
                write_evidence()
                return state

            try:
                compositor = spawn("swayfx", ["swayfx", "-c", str(sway_config)])

                def compositor_ready():
                    sockets = list(runtime.glob("sway-ipc*.sock"))
                    displays = [path for path in runtime.glob("wayland-*")
                                if path.is_socket()]
                    return (sockets[0], displays[0].name) if sockets and displays else None

                sway_socket, wayland_display = wait_for(
                    compositor_ready, "private compositor did not become ready"
                )
                env["SWAYSOCK"] = str(sway_socket)
                env["WAYLAND_DISPLAY"] = wayland_display
                connection = SwayIPC(sway_socket)
                spawn("fixture-top", [sys.executable, str(Path(__file__).resolve()),
                                      "--fixture-panel"])
                wait_for(lambda: any(item["namespace"] == "attachment-fixture-top"
                         for output_node in ipc("get_outputs")
                         for item in output_node.get("layer_shell_surfaces", [])),
                         "exclusive top fixture did not appear")

                def terminal(app_id, title):
                    return spawn(app_id, ["foot", "--config", str(foot_config),
                        "--override", "colors-dark.background=" + (
                            "47365d" if app_id == "attachment-floating" else "33445b"),
                        "--app-id", app_id, "--title", title, "sh", "-c",
                        "printf '%s\\n' 'Private test window' 'Geometry and focus only'; sleep 300"])

                terminal("attachment-tiled", "Tiled reference window")
                tiled = wait_for(lambda: node("attachment-tiled"), "tiled client missing")
                baseline = tiled["rect"]
                require(baseline == {"x": 0, "y": TOP_ZONE, "width": WIDTH,
                                     "height": HEIGHT - TOP_ZONE},
                        f"exclusive top fixture did not reserve expected space: {baseline}")
                terminal("attachment-floating", "Floating attachment preview")
                floating = wait_for(lambda: node("attachment-floating"), "floating client missing")
                floating_id, tiled_id = floating["id"], tiled["id"]
                spawn("decoration", [str(HELPER), "daemon"])
                initial = capture("attached-bottom", lambda state: attached(state, "bottom")
                        and state["clients"]["attachment-tiled"]["rect"] == baseline,
                        "bottom caption did not attach flush without reserving workspace space")

                for app_id, label in (("com.mbp-intel.dropdown", "ghostty"),
                                      ("mbp-intel-dropdown", "legacy-foot"),
                                      ("com.mbp-intel.monitor", "monitor")):
                    terminal(app_id, "Private drop-down console")
                    console = wait_for(lambda: node(app_id), "drop-down client missing")
                    ipc(command=f'[con_id={console["id"]}] floating enable, '
                                'resize set 1000 220, move absolute position 100 60, focus')
                    capture("dropdown-" + label + "-keeps-ordinary-caption", lambda state:
                            attached(state, "bottom") and state["clients"][app_id]["focused"],
                            "console focus moved the ordinary window caption")
                    ipc(command=f'[con_id={console["id"]}] move scratchpad')
                    capture("dropdown-" + label + "-hide-keeps-caption", lambda state:
                            attached(state, "bottom")
                            and state["clients"]["attachment-floating"]["focused"],
                            "hiding the console did not retain ordinary caption focus")
                    expected_exits.add(app_id)
                    ipc(command=f'[con_id={console["id"]}] kill')

                pointer = spawn("pointer", [str(pointer_binary)], pointer=True)
                pointer_reply(pointer, "ready")

                def event(command):
                    pointer.stdin.write(command + "\n")
                    pointer.stdin.flush()
                    pointer_reply(pointer, "ok")

                def move_pointer(x, y):
                    event(f"move {round(x * 800 / WIDTH)} {round(y * 600 / HEIGHT)}")

                terminal("attachment-hover", "Second floating hover target")
                hover = wait_for(lambda: node("attachment-hover"), "hover client missing")
                second = capture("hover-target-bottom", lambda state:
                        attached(state, "bottom", "attachment-hover"),
                        "second floating caption did not settle")
                move_pointer(1000, 200)
                ipc(command="focus_follows_mouse yes")
                handoffs = []
                evidence["hover_handoffs"] = handoffs
                targets = [("attachment-floating", (300, 240), 0.25),
                           ("attachment-hover", (1000, 200), 0.25),
                           ("attachment-floating", (300, 240), 0.25)]
                targets += [("attachment-hover", (1000, 200), 0.08),
                            ("attachment-floating", (300, 240), 0.08)] * 3
                complete_rects = (None, initial["caption_global_rect"], second["caption_global_rect"])
                for app_id, pointer_position, duration in targets:
                    before = snapshot()["caption_global_rect"]
                    expected = dict((initial if app_id == "attachment-floating" else second)
                                    ["caption_global_rect"])
                    started = time.monotonic()
                    move_pointer(*pointer_position)
                    samples = []
                    while time.monotonic() - started < duration:
                        state = snapshot()
                        visible_rect = state["caption_global_rect"]
                        if visible_rect and (visible_rect["width"] <= 0 or visible_rect["height"] <= 0):
                            visible_rect = None
                        samples.append({"elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                                        "caption_rect": visible_rect,
                                        "caption_count": len(state["captions"]),
                                        "target_focused": state["clients"][app_id]["focused"]})
                        time.sleep(0.004)
                    handoffs.append({"target": app_id, "before": before,
                                     "expected": expected, "duration_seconds": duration,
                                     "first_complete_ms": next((sample["elapsed_ms"]
                                         for sample in samples if sample["caption_rect"] == expected), None),
                                     "samples": samples})
                    write_evidence()
                    require(samples[-1]["target_focused"]
                            and (duration < 0.25 or samples[-1]["caption_rect"] == expected),
                            "hover focus did not attach to the new target")
                    require(all(sample["caption_count"] <= 1
                                and sample["caption_rect"] in complete_rects
                                for sample in samples),
                            "hover handoff rendered an intermediate position or size")
                checks.append("hover-handoffs-have-no-intermediate-geometry")
                capture("hover-return-bottom", lambda state: attached(state, "bottom"),
                        "hover return did not keep the original attachment")
                ipc(command="focus_follows_mouse no")
                expected_exits.add("attachment-hover")
                ipc(command=f'[con_id={hover["id"]}] kill')

                rect = initial["clients"]["attachment-floating"]["rect"]
                drag_keyboard = spawn("drag-keyboard", ["wtype", "-M", "logo", "-s", "2000", "-m", "logo"])
                time.sleep(0.15)
                move_pointer(rect["x"] + 100, rect["y"] + 80)
                event("press 272")
                try:
                    move_pointer(rect["x"] + 200, rect["y"] + 150)
                    started = time.monotonic()
                    drag_samples = []
                    evidence["drag_samples"] = drag_samples

                    def follows_held_drag():
                        state = snapshot()
                        states["drag-last-observation"] = state
                        drag_samples.append({
                            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                            "client_rect": state["clients"]["attachment-floating"]["rect"],
                            "caption_rect": state["caption_global_rect"],
                        })
                        moved = state["clients"]["attachment-floating"]["rect"]["x"] != rect["x"]
                        return state if moved and attached(state, "bottom") else None

                    held = wait_for(follows_held_drag,
                                    "caption did not follow an active pointer drag within 250ms",
                                    seconds=0.25, interval=0.004)
                    evidence["drag_follow_ms"] = round((time.monotonic() - started) * 1000, 1)
                    states["drag-tracks-before-release"] = held
                    checks.append("drag-tracks-before-release")
                    final_x = held["caption_global_rect"]["x"]
                    require(any(sample["caption_rect"] is not None
                                and min(rect["x"], final_x) < sample["caption_rect"]["x"]
                                < max(rect["x"], final_x) for sample in drag_samples),
                            "caption jumped directly to the moved window without an animation frame")
                    checks.append("drag-renders-intermediate-animation-frame")
                finally:
                    event("release 272")
                    expected_exits.add("drag-keyboard")
                    drag_keyboard.terminate()
                    drag_keyboard.wait(timeout=3)
                capture("dragged-bottom", lambda state: attached(state, "bottom"),
                        "releasing the pointer detached the caption")
                ipc(command=f"[con_id={floating_id}] resize set 220 180")
                capture("small-bottom", lambda state: attached(state, "bottom")
                        and state["clients"]["attachment-floating"]["rect"]["width"] == 220,
                        "small bottom caption kept a stale GTK minimum width")
                ipc(command=f"[con_id={floating_id}] resize set 740 420, move absolute position 340 230")
                capture("moved-resized-bottom", lambda state: attached(state, "bottom")
                        and state["clients"]["attachment-floating"]["rect"] ==
                        {"x": 340, "y": 230, "width": 740, "height": 420}
                        and state["clients"]["attachment-tiled"]["rect"] == baseline,
                        "attachment did not track moving and resizing the float")
                subprocess.run([str(HELPER), "right"], env=env, stdout=log,
                               stderr=log, check=True, timeout=5)
                capture("attached-right", lambda state: attached(state, "right")
                        and state["clients"]["attachment-tiled"]["rect"] == baseline,
                        "saved right placement did not follow the floating edge")
                ipc(command=f"[con_id={floating_id}] resize set 220 180")
                capture("small-right", lambda state: attached(state, "right")
                        and state["clients"]["attachment-floating"]["rect"]["height"] == 180,
                        "small right caption kept a stale GTK minimum height")
                ipc(command=f"[con_id={floating_id}] resize set 740 420")
                capture("right-size-restored", lambda state: attached(state, "right"),
                        "growing the floating client lost right attachment")

                ipc(command=f"[con_id={tiled_id}] fullscreen enable")
                fullscreen = capture("fullscreen-forces-bottom", lambda state:
                    workspace_edge(state, "bottom")
                    and state["clients"]["attachment-tiled"]["fullscreen_mode"] == 1,
                    "fullscreen did not force a single output-wide bottom caption")
                require(json.loads(preferences.read_text())["position"] == "right",
                        "fullscreen overwrote the preferred right placement")
                require(fullscreen["captions"][0]["effects"]["corner_radius"] == 0,
                        "compositor forces rounded corners on the fullscreen caption")
                checks.append("fullscreen-preserves-preferred-edge-and-compositor-square-corners")
                pixels = bottom_corner_pixels(output / "fullscreen-forces-bottom.png",
                                               fullscreen["captions"][0]["extent"])
                require(pixels["left_corner"] == pixels["left_inset"]
                        and pixels["right_corner"] == pixels["right_inset"],
                        f"fullscreen tiled caption still has rounded bottom corners: {pixels}")
                evidence["fullscreen_square_pixels"] = pixels
                checks.append("fullscreen-tiled-bottom-corners-render-square")
                ipc(command=f"[con_id={tiled_id}] fullscreen disable; [con_id={floating_id}] focus")
                capture("fullscreen-exit-restores-right", lambda state: attached(state, "right"),
                        "leaving fullscreen did not restore right attachment")

                ipc(command=f"[con_id={floating_id}] fullscreen enable")
                floating_fullscreen = capture("floating-fullscreen-forces-bottom", lambda state:
                        workspace_edge(state, "bottom")
                        and state["clients"]["attachment-floating"]["fullscreen_mode"] == 1,
                        "a fullscreen floating view did not return the caption to the bottom")
                pixels = bottom_corner_pixels(output / "floating-fullscreen-forces-bottom.png",
                                               floating_fullscreen["captions"][0]["extent"])
                require(pixels["left_corner"] != pixels["left_inset"]
                        and pixels["right_corner"] != pixels["right_inset"],
                        f"floating fullscreen lost its configured rounded corners: {pixels}")
                evidence["floating_fullscreen_round_pixels"] = pixels
                checks.append("floating-fullscreen-retains-rounded-bottom-corners")
                ipc(command=f"[con_id={floating_id}] fullscreen disable")
                capture("floating-fullscreen-exit-restores-right", lambda state: attached(state, "right"),
                        "leaving floating fullscreen did not restore the saved right attachment")

                ipc(command="output HEADLESS-1 position -1440 -120")
                capture("negative-output-origin", lambda state: attached(state, "right")
                        and state["output"]["x"] == -1440 and state["output"]["y"] == -120,
                        "negative output origin offset the attached caption")
                ipc(command="output HEADLESS-1 position 0 0")
                right = capture("origin-restored", lambda state: attached(state, "right")
                                and state["output"]["x"] == state["output"]["y"] == 0,
                                "restoring the output origin broke attachment")

                rect = right["caption_global_rect"]
                move_pointer(rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2)
                event("press 274")
                event("release 274")
                capture("middle-click-tiles-target", lambda state: workspace_edge(state, "right")
                        and state["clients"]["attachment-floating"]["floating"].endswith("_off"),
                        "middle-click did not tile the attached client and restore workspace chrome")

                ipc(command=f"[con_id={floating_id}] floating enable, resize set 740 420, move absolute position 340 230, focus")
                capture("float-restores-attachment", lambda state: attached(state, "right"),
                        "floating the client again did not restore attachment")
                ipc(command="workspace 2")
                capture("empty-workspace-edge", lambda state: workspace_edge(state, "right")
                        and any(item["name"] == "2" and item["focused"]
                                for item in state["workspaces"]),
                        "changing to an empty workspace left a stale floating caption")
                ipc(command=f"workspace 1; [con_id={floating_id}] focus")
                capture("workspace-return-attachment", lambda state: attached(state, "right"),
                        "returning to the floating workspace did not restore attachment")
                ipc(command=f"[con_id={tiled_id}] focus")
                capture("tiled-focus-restores-workspace-edge", lambda state: workspace_edge(state, "right")
                        and state["clients"]["attachment-tiled"]["focused"],
                        "focusing a tiled sibling left a floating attachment behind")
                ipc(command=f"[con_id={floating_id}] focus")
                capture("floating-focus-restores-attachment", lambda state: attached(state, "right"),
                        "refocusing the floating sibling did not restore its caption")
                expected_exits.add("attachment-floating")
                ipc(command=f"[con_id={floating_id}] kill")
                capture("destroy-restores-workspace-edge", lambda state: workspace_edge(state, "right")
                        and "attachment-floating" not in state["clients"],
                        "destroying the float left a stale caption or duplicate surfaces")
                require(source_hashes() == evidence["source_sha256"],
                        "decoration source changed during native verification")
                evidence["status"] = "passed"
                write_evidence()
            except BaseException as error:
                evidence["status"] = "failed"
                evidence["error"] = str(error)
                write_evidence()
                traceback.print_exc()
                raise
            finally:
                if connection is not None:
                    connection.close()
                for _name, process in reversed(processes):
                    # The shell/fixture may have exited before its children.
                    # Each fixture owns a new process group, so clean that group
                    # even when its leader has already been reaped.
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    if process.poll() is None:
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            pass
                    # A child can ignore TERM after its leader has exited.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                    for stream in (process.stdin, process.stdout):
                        if stream is not None:
                            stream.close()
    print(output)


def enter_private_bus():
    if os.environ.get(PRIVATE_BUS_MARKER) == "1":
        require("DBUS_SESSION_BUS_ADDRESS" in os.environ, "private D-Bus is missing")
        return
    env = dict(os.environ)
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    env[PRIVATE_BUS_MARKER] = "1"
    os.execvpe("dbus-run-session", ["dbus-run-session", "--", sys.executable,
                str(Path(__file__).resolve()), *sys.argv[1:]], env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixture-panel", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.fixture_panel:
        fixture_panel()
        return
    if args.output is None:
        parser.error("--output is required")
    enter_private_bus()
    run_verifier(args.output)


if __name__ == "__main__":
    main()
