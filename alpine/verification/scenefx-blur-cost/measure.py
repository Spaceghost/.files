#!/usr/bin/env python3
"""Measure what a damaging BOTTOM-layer surface costs a private headless SwayFX.

Never touches the live session: private XDG_RUNTIME_DIR, headless backend, and
the idle Intel render node (the live compositor renders on the Radeon).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]                       # .../alpine/verification/<this> -> checkout root
LAYERANIM = Path(os.environ.get("LAYERANIM", HERE / "layeranim"))
CARD = Path("/sys/class/drm/card1")          # i915, Iris Pro 5200, idle
RENDER_NODE = "/dev/dri/renderD128"          # i915 render node
TICKS = os.sysconf("SC_CLK_TCK")

BASE_EFFECTS = """corner_radius 22
smart_corner_radius disable
blur {blur}
blur_xray {xray}
blur_passes {passes}
blur_radius {radius}
blur_noise {noise}
blur_brightness {brightness}
blur_contrast {contrast}
blur_saturation {saturation}
shadows {shadows}
shadows_on_csd enable
shadow_blur_radius 34
shadow_color #1d2021b8
shadow_inactive_color #1d202190
shadow_offset 0 10
default_dim_inactive 0.02
dim_inactive_colors.unfocused #282828ff
titlebar_separator disable
animation_duration_ms 140
layer_effects "measure-anim" {{
    blur disable
    shadows disable
    corner_radius 0
}}
"""


def cpu_ticks(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    except (OSError, IndexError):
        return None
    return int(fields[11]) + int(fields[12])       # utime + stime


def rc6_ms():
    try:
        return int((CARD / "power/rc6_residency_ms").read_text())
    except OSError:
        return None


def act_freq():
    try:
        return int((CARD / "gt_act_freq_mhz").read_text())
    except OSError:
        return None


def run_case(case, out_dir):
    label = case["label"]
    work = out_dir / label
    work.mkdir(parents=True, exist_ok=True)
    effects = work / "effects.conf"
    effects.write_text(BASE_EFFECTS.format(
        blur=case.get("blur", "enable"), xray=case.get("xray", "disable"),
        passes=case.get("passes", 1), radius=case.get("radius", 4),
        noise=case.get("noise", 0.012), brightness=case.get("brightness", 0.94),
        contrast=case.get("contrast", 1.03), saturation=case.get("saturation", 1.00),
        shadows=case.get("shadows", "enable")))
    config = work / "sway.conf"
    wallpaper = REPO / "alpine/assets/spaceghost.png"
    config.write_text(f'''xwayland disable
output HEADLESS-1 mode {case.get("mode", "2880x1800")}
output HEADLESS-1 scale {case.get("scale", 2)}
output * bg "{wallpaper}" fill
default_border none
gaps inner 13
font pango:monospace 10
include "{effects}"
''')
    foot_ini = work / "foot.ini"
    foot_ini.write_text("[main]\nfont=monospace:size=11\npad=24x24\n"
                        "[colors-dark]\nalpha=0.78\nbackground=10091d\nforeground=f4eaff\n")

    runtime = tempfile.mkdtemp(prefix="blurcost-rt-")
    env = dict(os.environ)
    env.update(XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless", WLR_HEADLESS_OUTPUTS="1",
               WLR_RENDERER="gles2", WLR_RENDERER_ALLOW_SOFTWARE="1",
               WLR_RENDER_DRM_DEVICE=RENDER_NODE,
               LAYERANIM_SCALE=str(case.get("scale", 2)))
    if case.get("wlr_renderer"):
        env["WLR_RENDERER"] = case["wlr_renderer"]
    if case.get("render_device"):
        env["WLR_RENDER_DRM_DEVICE"] = case["render_device"]
    for key in ("SWAYSOCK", "WAYLAND_DISPLAY", "DISPLAY"):
        env.pop(key, None)

    log_path = work / "compositor.log"
    result = {"case": case}
    with log_path.open("w") as log:
        subprocess.run(["/usr/bin/swayfx", "--validate", "--config", str(config)],
                       env=env, stdout=log, stderr=log, check=True)
        comp = subprocess.Popen(["/usr/bin/swayfx", "--debug", "--config", str(config)],
                                env=env, stdout=log, stderr=log)
        clients = []
        try:
            for _ in range(200):
                if comp.poll() is not None:
                    raise RuntimeError("compositor exited early; see " + str(log_path))
                socks = list(Path(runtime).glob("sway-ipc*.sock"))
                disps = [p for p in Path(runtime).glob("wayland-*") if p.suffix != ".lock"]
                if socks and disps:
                    env.update(SWAYSOCK=str(socks[0]), WAYLAND_DISPLAY=disps[0].name)
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("timed out waiting for private compositor")

            for _ in range(case.get("windows", 1)):
                clients.append(subprocess.Popen(
                    ["foot", "--config", str(foot_ini), "--app-id=blurcost",
                     "sh", "-c", "printf 'blurcost fixture\\n'; sleep 600"],
                    env=env, stdout=log, stderr=log))
                time.sleep(1.2)
            time.sleep(1.5)

            anim = None
            if case.get("rate", 0) > 0 or case.get("map_surface", True):
                cmd = [str(LAYERANIM), "--mode", case.get("anim_mode", "timer"),
                       "--layer", case.get("layer", "bottom"),
                       "--rate", str(case.get("rate", 0) or 0.05),
                       "--damage", case.get("damage", "200x200"),
                       "--duration", str(case["duration"] + case.get("settle", 2) + 1),
                       "--namespace", "measure-anim"]
                anim = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=log, text=True)
                clients.append(anim)
            time.sleep(case.get("settle", 2))

            t0 = time.monotonic(); c0 = cpu_ticks(comp.pid); r0 = rc6_ms()
            freqs = []
            deadline = t0 + case["duration"]
            while time.monotonic() < deadline:
                freqs.append(act_freq())
                time.sleep(0.05)
            t1 = time.monotonic(); c1 = cpu_ticks(comp.pid); r1 = rc6_ms()

            wall = t1 - t0
            comp_cpu = (c1 - c0) / TICKS / wall
            gpu_busy = None
            if r0 is not None and r1 is not None:
                gpu_busy = max(0.0, 1.0 - ((r1 - r0) / 1000.0) / wall)
            freqs = [f for f in freqs if f is not None]
            result.update(wall_s=round(wall, 3),
                          compositor_cpu_frac=round(comp_cpu, 4),
                          gpu_busy_frac=round(gpu_busy, 4) if gpu_busy is not None else None,
                          gpu_freq_mean_mhz=round(sum(freqs) / len(freqs), 1) if freqs else None,
                          gpu_freq_max_mhz=max(freqs) if freqs else None,
                          rc6_delta_ms=(r1 - r0) if r0 is not None else None)

            if case.get("screenshot"):
                shot = work / "screenshot.png"
                subprocess.run(["grim", str(shot)], env=env, check=False)
                result["screenshot"] = str(shot)

            if anim is not None:
                try:
                    out, _ = anim.communicate(timeout=10)
                    if out and out.strip():
                        aj = json.loads(out.strip().splitlines()[-1])
                        result["animator"] = aj
                        if case.get("anim_mode") == "callback" and aj.get("commit_hz"):
                            result["composite_fps"] = aj["commit_hz"]
                            result["frame_ms"] = round(1000.0 / aj["commit_hz"], 3)
                            result["cpu_ms_per_frame"] = round(
                                result["compositor_cpu_frac"] * 1000.0 / aj["commit_hz"], 3)
                except Exception as exc:
                    result["animator_error"] = repr(exc)
        finally:
            for c in clients:
                if c.poll() is None:
                    c.terminate()
                    try: c.wait(timeout=5)
                    except Exception: c.kill()
            if comp.poll() is None:
                comp.terminate()
                try: comp.wait(timeout=6)
                except Exception: comp.kill()
            shutil.rmtree(runtime, ignore_errors=True)

    text = log_path.read_text(errors="replace")
    result["renderer"] = next((l for l in text.splitlines() if "GLES" in l or "renderer" in l.lower()), "")[:200]
    for key, pat in (("gl_renderer", r"GL renderer: (.*)"), ("gl_vendor", r"GL vendor: (.*)"),
                     ("scenefx", r"(scenefx \S+)")):
        m = re.search(pat, text)
        if m:
            result[key] = m.group(1).strip()
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="JSON file with a list of cases")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cases = json.loads(Path(args.cases).read_text())
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for case in cases:
        print(f"--- {case['label']}", flush=True)
        try:
            res = run_case(case, out_dir)
        except Exception as exc:
            res = {"case": case, "error": repr(exc)}
        results.append(res)
        print(json.dumps(res), flush=True)
        (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        time.sleep(3)   # let the GPU fall back to rc6 between runs
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
