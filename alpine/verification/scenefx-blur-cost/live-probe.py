#!/usr/bin/env python3
"""Measure the optimized-blur invalidation on the real panel and the real GPU.

The headless half of this study runs on the idle Intel render node. The live
desktop renders on the Radeon (card0, renderD129, eDP-1), so the headless
numbers describe a different GPU at a different clock. This script repeats the
same experiment where it actually matters, and only the user can run it: it
puts a surface into his running session.

What it does, for `--seconds` per phase:

  1. baseline  -- nothing mapped, just samples the counters
  2. top       -- a full-output layer surface on TOP, damaging a small
                  rectangle once per composite
  3. bottom    -- the same surface on BOTTOM, which is the layer SwayFX
                  invalidates the optimized blur from

`layeranim` in `--mode callback` commits exactly once per frame callback, so
its commit rate *is* the compositor's composite rate for that surface. TOP and
BOTTOM differ in nothing else.

What it costs while it runs: a translucent rectangle wanders under (BOTTOM) or
over (TOP) the windows, and during the BOTTOM phase the desktop will be less
responsive. Everything ends when the process does; it changes no configuration,
starts no service and installs nothing.

Read the result like this:

  * bottom_fps close to top_fps        -- the invalidation is cheap on this GPU
                                          and the animated planks are affordable
  * bottom_fps around 30-50, top_fps   -- the invalidation costs roughly a
    much higher                           frame; bursts only, no continuous motion
  * bottom_fps below 30                -- same conclusion as the headless run;
                                          animation on BOTTOM is not affordable

Usage:
    python3 alpine/verification/scenefx-blur-cost/live-probe.py \
        --layeranim /tmp/layeranim --seconds 10 --out /tmp/live-probe.json

Build `layeranim` first (one C file, links only libwayland-client, installs
nothing).  The layer-shell protocol description ships in the SwayFX source
tarball, so unpack that first and point the script at it:

    alpine/verification/scenefx-blur-cost/build-layeranim.sh \
        /path/to/swayfx-*/protocols/wlr-layer-shell-unstable-v1.xml
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

APPLESMC = Path("/sys/devices/platform/applesmc.768")
RADEON = Path("/sys/class/drm/card0/device")
TICKS = os.sysconf("SC_CLK_TCK")


def read_int(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def compositor_pid():
    out = subprocess.run(["pgrep", "-x", "swayfx"], capture_output=True, text=True)
    pids = [int(p) for p in out.stdout.split()]
    # the session compositor is the one holding the live SWAYSOCK, i.e. the
    # oldest swayfx that is not a private headless verifier
    for pid in sorted(pids):
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
        if "/run/user/" in cmd:
            return pid
    return pids[0] if pids else None


def cpu_ticks(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    except (OSError, IndexError):
        return None
    return int(fields[11]) + int(fields[12])


def gpu_mhz():
    for candidate in sorted(RADEON.glob("hwmon/hwmon*/freq1_input")):
        value = read_int(candidate)
        if value:
            return value / 1e6
    return None


def gpu_temp():
    for candidate in sorted(RADEON.glob("hwmon/hwmon*/temp1_input")):
        value = read_int(candidate)
        if value:
            return value / 1000.0
    return None


def sample():
    return {
        "gpu_mhz": gpu_mhz(),
        "gpu_temp_c": gpu_temp(),
        "fan1_rpm": read_int(APPLESMC / "fan1_input"),
        "fan2_rpm": read_int(APPLESMC / "fan2_input"),
        "loadavg": float(Path("/proc/loadavg").read_text().split()[0]),
    }


def phase(name, args, pid, layer=None):
    proc = None
    if layer is not None:
        proc = subprocess.Popen(
            [args.layeranim, "--mode", "callback", "--layer", layer,
             "--damage", args.damage, "--duration", str(args.seconds + 2),
             "--namespace", "blurcost-probe"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env=dict(os.environ, LAYERANIM_SCALE=str(args.scale)))
        time.sleep(1.5)          # let it map and settle before the window opens

    before, t0, c0 = sample(), time.monotonic(), cpu_ticks(pid)
    samples = []
    while time.monotonic() - t0 < args.seconds:
        samples.append(sample())
        time.sleep(0.1)
    t1, c1, after = time.monotonic(), cpu_ticks(pid), sample()
    wall = t1 - t0

    row = {
        "phase": name, "layer": layer, "wall_s": round(wall, 3),
        "compositor_cpu_frac": round((c1 - c0) / TICKS / wall, 4),
        "gpu_mhz_mean": round(sum(s["gpu_mhz"] for s in samples if s["gpu_mhz"])
                              / max(1, len([s for s in samples if s["gpu_mhz"]])), 1),
        "gpu_temp_c_before": before["gpu_temp_c"], "gpu_temp_c_after": after["gpu_temp_c"],
        "fan1_rpm_before": before["fan1_rpm"], "fan1_rpm_after": after["fan1_rpm"],
        "loadavg_before": before["loadavg"], "loadavg_after": after["loadavg"],
    }
    if proc is not None:
        try:
            out, _ = proc.communicate(timeout=args.seconds + 10)
            if out and out.strip():
                anim = json.loads(out.strip().splitlines()[-1])
                row["animator"] = anim
                row["composite_fps"] = anim.get("commit_hz")
                if anim.get("commit_hz"):
                    row["frame_ms"] = round(1000.0 / anim["commit_hz"], 3)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layeranim", required=True, help="path to the compiled layeranim binary")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--damage", default="200x200", help="logical damage rectangle per commit")
    ap.add_argument("--scale", type=int, default=2, help="output scale, 2 on eDP-1")
    ap.add_argument("--out", type=Path, default=Path("live-probe.json"))
    args = ap.parse_args()

    if not os.environ.get("WAYLAND_DISPLAY"):
        sys.exit("run this from inside the live session; WAYLAND_DISPLAY is unset")
    pid = compositor_pid()
    if pid is None:
        sys.exit("no running swayfx found")

    print(f"compositor pid {pid}; each phase takes about {args.seconds + 4:.0f}s")
    rows = [phase("baseline", args, pid, layer=None)]
    print(json.dumps(rows[-1]))
    for layer in ("top", "bottom"):
        rows.append(phase(layer, args, pid, layer=layer))
        print(json.dumps(rows[-1]))
        time.sleep(3)

    top = next((r for r in rows if r["layer"] == "top"), {})
    bottom = next((r for r in rows if r["layer"] == "bottom"), {})
    verdict = None
    if top.get("frame_ms") and bottom.get("frame_ms"):
        ratio = bottom["frame_ms"] / top["frame_ms"]
        verdict = {
            "top_frame_ms": top["frame_ms"], "bottom_frame_ms": bottom["frame_ms"],
            "ratio": round(ratio, 2),
            "invalidation_cost_ms": round(bottom["frame_ms"] - top["frame_ms"], 2),
            "bottom_holds_60hz": bottom["composite_fps"] >= 58,
        }
    payload = {"date": time.strftime("%Y-%m-%d"), "compositor_pid": pid,
               "phases": rows, "verdict": verdict}
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(verdict, indent=2))
    print(f"written to {args.out}")


if __name__ == "__main__":
    main()
