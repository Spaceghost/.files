# What an animating BOTTOM-layer surface costs — 2026-09-09

[`docs/superpowers/specs/2026-09-09-simulation-desktop.md`](../../../docs/superpowers/specs/2026-09-09-simulation-desktop.md)
names one guess as "the largest risk in this document" and makes plank 3 the
gate on it: *an animating `BOTTOM`-layer surface invalidates SceneFX's
pre-rendered optimized-blur buffer every frame, forcing a full-output
dual-Kawase pass for the life of the session.* This is that measurement.

## The answer, in one paragraph

**It is true, it is worse than the spec guessed, and it is not a blur problem.**
Every commit of a `BACKGROUND`- or `BOTTOM`-layer surface calls
`wlr_scene_optimized_blur_mark_dirty()` unconditionally
(`sway/desktop/layer_shell.c:337-352`), and that call reaches
`scene_damage_outputs()` with the blur node's own visibility — which, because
the node is the size of the output and nothing on this desktop is opaque, **is
the whole output**. So a twenty-by-twenty-pixel change on `BOTTOM` becomes a
full-output repaint of the entire scene, plus a full-output dual-Kawase blur,
plus two full-output framebuffer copies. Measured on a private headless SwayFX
at the panel's real 2880×1800 with the desktop's real effects settings, one
transparent 0.78-alpha terminal on screen, an identical damaging surface costs
**37.4 ms per frame on `BOTTOM` and 6.2 ms on `TOP`** — a 6.0× frame and
31 ms of penalty per commit — and a 20×20 damage rectangle costs exactly as
much as a 2880×1800 one, which is the escalation showing itself. Of that 31 ms
only **4.2 ms is the blur**; the other 27 ms is the forced whole-scene repaint,
which is why `blur disable`, `blur_xray`, `blur_radius 2`, `shadows disable`
and the spec's own `layer_effects "oldbook-edges" { blur disable }` all measure
within noise of doing nothing. Below about 5 Hz of commits the GPU still sleeps
between them; at 10 Hz it stops sleeping; above about 27 Hz the compositor
cannot keep up at all. **Plank 3 does not proceed as written on `BOTTOM`**, and
neither do planks 4 or 5 — but the same effects on the `TOP` layer, clipped to
the free region the design already has to compute, cost 6.2 ms a frame and hold
60 Hz comfortably.

## 1. Is it true? What the SceneFX 0.5 source says

Read from the pinned tarball this repository ships
(`alpine/packages/scenefx/APKBUILD`, sha512 `055511e8…`, extracted and patched
with all three `alpine/packages/scenefx/*.patch` exactly as `abuild` does) and
from the SwayFX 0.6 tree at `fd71a6bd`. Every line number below is the same in
the pristine and the patched tree.

### The invalidation is unconditional, and SwayFX owns it

SceneFX never marks the buffer dirty by itself. Only the compositor does, and
SwayFX calls `wlr_scene_optimized_blur_mark_dirty()` in exactly four places —
two config commands (`sway/commands/blur.c:35`, `sway/commands/blur_xray.c:19`),
a layer-surface destroy (`sway/desktop/layer_shell.c:314`), and the one below —
plus `wlr_scene_optimized_blur_set_size()` on arrange
(`sway/tree/arrange.c:339`), which marks it dirty when the size changes:

```c
/* sway/desktop/layer_shell.c:337 */
static void handle_surface_commit(struct wl_listener *listener, void *data) {
	struct sway_layer_surface *surface = wl_container_of(listener, surface, surface_commit);
	struct wlr_layer_surface_v1 *layer_surface = surface->layer_surface;

	// Rerender the optimized blur on change
	if (layer_surface->current.layer == ZWLR_LAYER_SHELL_V1_LAYER_BACKGROUND ||
		layer_surface->current.layer == ZWLR_LAYER_SHELL_V1_LAYER_BOTTOM) {
		if (surface->output) {
			wlr_scene_optimized_blur_mark_dirty(surface->output->layers.blur_layer);
		}
	}
```

There is no test of damage size, of the surface's `layer_effects`, of whether
blur is enabled, or of whether anything blurred is on screen. **One commit on
`BACKGROUND` or `BOTTOM` — any commit — invalidates the buffer.** The blur
layer node itself is created between `shell_bottom` and `tiling`
(`sway/tree/output.c:110-116`) and sized to the whole output
(`sway/tree/arrange.c:339`), which is what makes "everything below the windows"
mean the wallpaper, Conky, mpvpaper and the proposed `oldbook-edges`.

### Marking it dirty damages the whole output

```c
/* types/scene/wlr_scene.c:1316 */
void wlr_scene_optimized_blur_mark_dirty(struct wlr_scene_optimized_blur *blur_node) {
	if (blur_node && !blur_node->node.enabled) {
		return;
	}
	blur_node->dirty = true;
	scene_node_update(&blur_node->node, NULL);
}
```

`scene_node_update(node, NULL)` (`:827`) documents that a NULL damage means "the
previous node's visibility". The optimized-blur node *is* the output rectangle,
and its visibility is that rectangle minus opaque regions above it — and this
desktop has no opaque regions above it, because the terminals run at 0.78 and
the caption strip at 0.67. So the update region is the output, and `:862`
passes it to `scene_damage_outputs()`. The whole output is damaged.

`scene_node_update_iterator` then makes it worse on purpose:

```c
/* types/scene/wlr_scene.c:1714 */
	if (node->type == WLR_SCENE_NODE_OPTIMIZED_BLUR) {
		struct wlr_scene_optimized_blur *scene_blur = wlr_scene_optimized_blur_from_node(node);
		if (scene_blur->dirty) {
			// Restore the visible region back to default, without any opaque
			// regions. This ensures that all nodes below are fully re-rendered
			// and not culled by above nodes.
			pixman_region32_clear(data->visible);
			pixman_region32_copy(data->visible, data->update_region);
		}
	}
```

Opaque culling is deliberately switched off for everything under the blur
layer. Even a desktop that *did* have an opaque window could not cull the
backdrop on a frame where the buffer is dirty.

### And the blur that follows is never clipped to damage

```c
/* render/fx_renderer/fx_pass.c:1181 */
bool fx_render_pass_add_optimized_blur(...) {
	struct wlr_box dst_box = fx_options->tex_options.base.dst_box;   /* = the whole output */
	...
	pixman_region32_init_rect(&clip, dst_box.x, dst_box.y, dst_box.width, dst_box.height);
	struct fx_framebuffer *fx_buffer = get_main_buffer_blur(pass, &blur_options);
	if (fx_buffer != NULL) {
		fx_render_pass_read_to_buffer(pass, &clip, ...optimized_blur_buffer, fx_buffer);
		fx_render_pass_read_to_buffer(pass, &clip, ...optimized_no_blur_buffer, pass->buffer);
	}
```

`get_main_buffer_blur` (`:978`) then expands that region by
`blur_data_calc_size()` and runs `num_passes` downscales and `num_passes`
upscales, plus one `render_blur_effects` pass whenever brightness, contrast,
saturation or noise is non-neutral — which the desktop's `blur_brightness 0.94`
and `blur_contrast 1.03` make true. At `blur_passes 1` / `blur_radius 4` that
is, per invalidated frame:

| Pass | Pixels written, 5.184 Mpix output |
| --- | ---: |
| Kawase down ×1 | 1.30 Mpix |
| Kawase up ×1 | 5.18 Mpix |
| `render_blur_effects` (noise/brightness/contrast) | 5.18 Mpix |
| copy → `optimized_blur_buffer` | 5.18 Mpix |
| copy → `optimized_no_blur_buffer` | 5.18 Mpix |
| **optimized-blur total** | **22.0 Mpix** |

on top of re-rendering the whole scene, unculled, into a whole-output damage
region.

### One thing the spec did not know: the terminals already read this buffer

```c
/* sway/desktop/output.c:335 */
bool should_optimize_blur = config->blur_xray || !could_container_overlap(closest_con);
wlr_scene_blur_set_should_only_blur_bottom_layer(blur, should_optimize_blur);
```

`could_container_overlap` (`:236`) is false for a tiled container that is not
mid-animation. So on this desktop the tiled terminals *already* take the
optimized-blur path even with `blur_xray disable`. The buffer is not a
side-feature; it is the thing his windows are frosted from.

## 2. What it costs, measured

A private headless SwayFX, the installed `/usr/bin/swayfx 0.6-r4` against the
installed `scenefx 0.5-r0`, on the **Intel Iris Pro 5200** render node
(`/dev/dri/renderD128`), a 2880×1800 output at scale 2 — the panel's real pixel
count — with the desktop's real blur settings, one `foot` at `alpha=0.78`, and
`layer_effects "measure-anim" { blur disable; shadows disable; corner_radius 0 }`
exactly as the spec proposes for `oldbook-edges`. The animating client
(`layeranim.c`) is a raw `wlr-layer-shell` client with an empty input region and
exclusive zone 0; in `--mode callback` it repaints and commits once per frame
callback, so **its commit rate is the compositor's composite rate**.

Nothing about the live session was touched: private `XDG_RUNTIME_DIR`, headless
backend, and the Intel GPU, which the live session does not use (see *3*).

### The layer is the only variable

| Case | Composite fps | Frame | Compositor CPU | CPU/frame | GPU never idle |
| --- | ---: | ---: | ---: | ---: | ---: |
| `BOTTOM`, 200×200 logical damage, run 1 | 27.06 | **36.95 ms** | 8.0 % | 2.95 ms | 100 % |
| `BOTTOM`, 200×200 logical damage, run 2 | 26.49 | **37.75 ms** | 9.5 % | 3.58 ms | 100 % |
| `BACKGROUND`, 200×200 logical damage | 26.53 | 37.69 ms | 10.1 % | 3.80 ms | 100 % |
| `TOP`, 200×200 logical damage, run 1 | 170.34 | **5.87 ms** | 94.8 % | 5.57 ms | 40.7 % |
| `TOP`, 200×200 logical damage, run 2 | 153.41 | **6.52 ms** | 90.0 % | 5.87 ms | 30.6 % |
| `OVERLAY`, 200×200 logical damage | 136.32 | 7.34 ms | 84.4 % | 6.19 ms | 51.0 % |

**`BOTTOM` mean 37.35 ms, `TOP` mean 6.19 ms: a 6.0× frame, 31.16 ms of penalty
per commit.** `BACKGROUND` behaves as `BOTTOM`; `OVERLAY` behaves as `TOP`. The
compositor is not CPU-bound on `BOTTOM` — it spends 3 ms of CPU and 34 ms
somewhere else, with the GPU's RC6 residency at exactly zero.

### Damage size does not matter, which is the escalation

| Case | Frame | Compositor CPU/frame |
| --- | ---: | ---: |
| `BOTTOM`, 20×20 logical damage | **37.44 ms** | 3.27 ms |
| `BOTTOM`, 200×200 logical damage | 37.35 ms | 3.27 ms |
| `BOTTOM`, full-surface 2880×1800 damage | 42.64 ms | 15.00 ms |
| `TOP`, full-surface 2880×1800 damage | 35.42 ms | 18.25 ms |

Forty pixels of change costs the same as five million. (The full-surface rows
carry an extra 12-15 ms of CPU that is the 19.8 MiB shm upload, not the
compositor's rendering; that is why `TOP` with full damage lands near `BOTTOM`
with none — a genuinely full-output repaint is a genuinely full-output repaint
whichever layer asks for it.)

### It is mostly not the blur

| Case | Frame | Penalty vs. the matching `TOP` run |
| --- | ---: | ---: |
| `BOTTOM`, blur as configured | 37.35 ms | 31.16 ms |
| `BOTTOM`, `blur disable` (globally) | 33.19 ms | 26.60 ms |
| `BOTTOM`, no blurred window on screen at all | 27.72 ms | 20.91 ms |
| `TOP`, `blur disable` | 6.59 ms | — |
| `TOP`, no blurred window on screen at all | 6.82 ms | — |

With blur switched off entirely, 26.6 ms of the 31.2 ms penalty survives.
With no blurred window on screen — where `fx_pass->has_blur` is false and the
optimized-blur pass provably does not run (`types/scene/wlr_scene.c:2166`) —
20.9 ms survives. **The dual-Kawase work is 4.2 ms of a 31 ms problem. The
problem is that damage tracking is switched off.**

### Nothing you can configure fixes it

| Change | Frame on `BOTTOM` | Verdict |
| --- | ---: | --- |
| baseline (`blur_passes 1`, `blur_radius 4`) | 37.35 ms | — |
| `layer_effects "…" { blur disable }` on the animating surface | 37.35 ms | present in **every** run above; does nothing |
| `blur_xray enable` | 37.64 ms | nothing |
| `blur_radius 2` | 38.43 ms | nothing |
| `blur_passes 2` | 40.47 ms | worse, as expected |
| `shadows disable` | 38.74 ms | nothing |
| blur effects neutral (`noise 0`, brightness/contrast/saturation 1.0) | 34.19 ms | saves 3.2 ms; costs the frosted-glass tint |
| `blur disable` globally | 33.19 ms | saves 4.2 ms; costs every frosted surface |
| **move the surface to `TOP`** | **6.19 ms** | **the only thing that works** |

An opaque region hint would not help either: `scene_node_update_iterator`
(`:1714`) explicitly clears the visible region when the node is dirty, so
opaque culling is off by construction on exactly the frames that are expensive.

### The rate sweep, against a 60 Hz output

Same fixture, output at 2880×1800@60Hz, animator on a fixed timer rather than
frame callbacks. "GPU never idle" is `1 − Δrc6_residency_ms / Δwall`; it is a
residency measure, not a utilisation measure, so it saturates — but the shape is
the answer.

| Commit rate on `BOTTOM` | Compositor CPU | CPU per invalidation | GPU never idle |
| ---: | ---: | ---: | ---: |
| 0 Hz (static surface, mapped) | 0.0 % | — | **0.4 %** |
| 1 Hz | 1.0 % | 9.90 ms | 14.0 % |
| 2 Hz | 1.9 % | 9.35 ms | 21.1 % |
| 5 Hz | 5.0 % | 10.00 ms | 42.3 % |
| 10 Hz | 8.6 % | 8.58 ms | **92.7 %** |
| 15 Hz | 10.7 % | 7.13 ms | **100 %** |
| 20 Hz | 9.2 % | 4.62 ms | 100 % |
| 30 Hz | 11.3 % | 3.77 ms | 100 % |
| 60 Hz | 11.2 % | 1.86 ms | 100 % |
| — | | | |
| `TOP` at 0 Hz | 0.0 % | — | 0.4 % |
| `TOP` at 15 Hz | 14.0 % | 9.33 ms | 14.7 % |
| `TOP` at 60 Hz | 44.0 % | 7.33 ms | **19.0 %** |

At 20 Hz and above the requested rate is fiction: the compositor tops out near
27 composites a second, so the per-invalidation CPU figure falls only because
invalidations are being coalesced. `TOP` at 60 Hz keeps up, on 44 % of one core
and a GPU that is asleep four fifths of the time.

**A static surface on `BOTTOM` is free.** 0.0 % CPU and 0.4 % GPU with the
surface mapped and never committing. Plank 1 as the other agent has built it —
`edges_surface.py`, Qt Quick, painting only on discrete events — costs one
invalidation per event and nothing at rest.

## 3. What the headless environment could not tell me

**The premise that headless means pixman means no blur is wrong, and that is
worth fixing wherever it is written.** `alpine/packages/swayfx/verify-window-animations:365`
records `"renderer": "pixman (software); blur and shadows are not exercised
headlessly"`, and `alpine/verification/decoration-framerate/README.md` had
already noticed that SwayFX creates its SceneFX renderer directly and ignores
`WLR_RENDERER`. I confirmed it: a run with `WLR_RENDERER=pixman` explicitly set
still logged `Creating scenefx FX renderer` / `GL renderer: Mesa Intel(R)
Iris(R) Pro Graphics P5200 (HSW GT3)` / `FX RENDERER: Shaders Initialized
Successfully` and produced a frame time of 38.48 ms against 38.21 ms for the
same case with `WLR_RENDERER=gles2` — identical within noise
(`results-renderer-selector.json`, `compositor-bottom.log`). What actually
selects the GPU is `WLR_RENDER_DRM_DEVICE`. `blurred-bottom-animating.png` is a
`grim` capture from one of these runs: a blurred painting, a 0.78-alpha
terminal, rounded corners, and the animator's rectangles blurred underneath.
The blur is real and the headless environment measures it.

What it still cannot tell you:

**It is the wrong GPU.** eDP-1 is a **`card0`** connector and `card0` is the
**radeon** (`DRIVER=radeon`, `PCI_ID=1002:6821`, `0000:01:00.0`); `card1` is the
i915 Iris Pro (`8086:0D26`, `0000:00:02.0`) with all four of its connectors
disconnected and `gt_act_freq_mhz` reading 0 while the desktop is up. The spec's
*Ground truth* section has these the wrong way round — it says eDP-1 hangs off
`card0`, `i915`, the Iris Pro, and that the Radeon has no connected connector.
**The live desktop renders and scans out on the Radeon.** I measured on the
Intel node precisely because it is idle and therefore does not contend with his
session, which means every absolute millisecond here belongs to a GPU his
desktop does not use.

**The Intel GT never left its floor clock.** `gt_act_freq_mhz` averaged 150 MHz
with a 150 MHz maximum across every run; `rps_min_freq_mhz` is 200,
`rps_RP0_freq_mhz` is 1200, and `rps_up_threshold_pct` is 95, so the governor
never boosted. Raising the floor needs root. So the absolute figures are a
**floor-clock** measurement and a pessimistic bound; the 6.0× ratio, the
damage-size independence and the blur-versus-repaint split are what transfer.

**No software cursor.** `screen-corners.patch` calls
`wlr_output_lock_software_cursors(wlr_output, true)`, so on the live desktop
every pointer move already forces a full-output recomposite. Headless has no
pointer. For plank 5 the two costs are additive, and this measurement contains
neither of them.

**Headless frame timing is not scanout.** As
`alpine/verification/decoration-framerate/README.md` records, the wlroots 0.20.2
headless output rearms an integer-millisecond timer after committing, so a
"frame" here is render + commit + that timer, adding roughly 1 ms at the
1000 Hz mode used for the maximum-rate runs. That is noise at 37 ms and about
17 % at 6 ms, which makes the 6.0× ratio a slight *under*statement.

**A much emptier desktop.** One window, one output, no Conky, no Waybar, no
caption strip, no Scripture bar, no notification daemon. Every one of those is a
scene node that the real compositor re-renders on every invalidated frame, so
the real full-output repaint is more expensive than this one, not less.

**A loaded host.** Concurrent sessions kept the load average between 8 and 14 on
8 threads with both fans pinned (6157 and 5701 rpm, `fan1_max` 6156) and the
Radeon at 74 °C throughout. Nothing else used `renderD128`, so the GPU figures
are isolated; the CPU figures are contended and should be read as upper bounds.
The two repeated cases differ by 2 % (`BOTTOM`) and 11 % (`TOP`).

### The measurement only he can run

`live-probe.py` in this directory repeats exactly this experiment against the
running session and the Radeon. It runs three phases — nothing, `TOP`, `BOTTOM` —
with the same `layeranim` binary in `--mode callback`, and records the
compositor's CPU, the Radeon's `freq1_input` and `temp1_input`, both fan
speeds, and the achieved composite rate. It changes no configuration, starts no
service, installs nothing, and ends when the process does; while it runs, a
translucent rectangle wanders under (or over) the windows and the `BOTTOM`
phase will feel less responsive.

```sh
# one C file, links only libwayland-client, nothing installed
alpine/verification/scenefx-blur-cost/build-layeranim.sh \
    /path/to/swayfx-*/protocols/wlr-layer-shell-unstable-v1.xml
python3 alpine/verification/scenefx-blur-cost/live-probe.py \
    --layeranim /tmp/layeranim --seconds 10 --out /tmp/live-probe.json
```

Turn off `oldbook-video-background` first if it is running; it is the other
tenant of `BOTTOM`. Read the result from `verdict`:

| `bottom_frame_ms` | Means |
| --- | --- |
| within ~30 % of `top_frame_ms` | The Radeon absorbs the invalidation. Planks 3-5 become a budget question rather than a design question, and this whole document is an Iris Pro story. |
| 2-4× `top_frame_ms`, `bottom` still ≥ 58 fps | It costs a real fraction of a frame but 60 Hz holds. Bursts are fine; continuous motion spends a third of the GPU for the session. |
| `bottom` below 58 fps | The headless conclusion stands on the real GPU. `BOTTOM` cannot animate. |

The one number that decides it is `bottom_holds_60hz`.

## 4. Thresholds

At 37.35 ms per invalidation on the measured GPU:

- **0 commits/s — free.** A static `BOTTOM` surface costs nothing at rest:
  0.0 % CPU, 0.4 % GPU. Plank 1 is safe as built.
- **1-5 commits/s — a real but intermittent cost.** ~10 ms of compositor CPU
  each, and the GPU still sleeps 58-86 % of the time. This is the rate at which
  discrete, event-driven redraws live, and it is affordable.
- **~10 commits/s — the GPU stops sleeping** (92.7 % never-idle at 10 Hz,
  100 % at 15 Hz). This is the threshold at which "it stops mattering" reverses
  into "it always matters".
- **~27 commits/s — the ceiling.** Above this the compositor simply cannot
  produce frames; a request for 60 fps yields 27 fps and a saturated GPU.

**Bursty is better than continuous, but not by as much as the spec hopes.**
Burstiness changes the duty cycle, not the per-frame cost, so the arithmetic is
direct:

| Spec animation | Frames at 60 fps | Actual wall time | Achieved rate |
| --- | ---: | ---: | ---: |
| Effect 3's 180 ms cross-fade (plank 3) | 11 | **411 ms** | 27 fps |
| Effect 1's 320 ms pulse decay (plank 4) | 19 | **710 ms** | 27 fps |
| Effect 5's 260 ms window wake (plank 4) | 16 | **598 ms** | 27 fps |
| Effect 2's pointer parallax (plank 5) | continuous while moving | — | 27 fps, GPU pegged |

Every bounded animation takes 2.3× longer than designed and runs at 27 fps
while it does — and a 180 ms cross-fade that actually lasts 411 ms is not the
motion that was specified. Pointer parallax is the worst case, because it is
not bursty in any useful sense: a pointer in motion generates motion events for
as long as it moves, and each one is an invalidation, on top of the full-output
recomposite the software cursor already forces.

The one honest way to make plank 3 affordable on `BOTTOM` is to **cap the
invalidation rate, not the animation**: a 180 ms cross-fade drawn as three
steps at 15 Hz costs three invalidations, about 112 ms of busy GPU, and looks
like a stepped dissolve rather than a fade. Whether that is worth having is an
aesthetic question, not a performance one.

## 5. Recommendation for plank 3

**Plank 3 does not proceed as written.** Neither do planks 4 or 5. The spec's
own contingency is the right one and should be taken: *"every effect stays in
its static form, which is what he asked for anyway."*

Concretely, for the agent building this:

1. **Planks 0, 1, 2 and effect 4 proceed unchanged.** They commit on discrete
   events — a layout change, a palette change, a painting change, a power
   posture change — at rates far below 1 Hz. One invalidation each, ~37 ms on
   the measured GPU and less on the Radeon, invisible. The static form is not a
   compromise here; it is the only form that is free.
2. **Keep the static surface genuinely static.** Because every commit costs a
   full-output repaint, `oldbook-edges` must not commit when nothing changed.
   In particular `oldbook-space`'s `IDLE_INTERVAL` republish at 1.33 Hz must not
   turn into a surface commit unless the occupancy grid actually differs. One
   invalidation a second measured at 14 % GPU never-idle and 1.0 % of a core, and
   that would be the price of a picture that did not change. The existing two-stage deduplication in
   `decoration_watch.TreeWatch` is exactly the right guard; make sure the
   drawing side has one too.
3. **If plank 3's cross-fade is wanted, move `oldbook-edges` to `TOP` and clip
   it to the free region.** This is the design change the measurement argues
   for, and it is smaller than it sounds: the surface already has to clip
   against Conky, Waybar, the caption strip and the Scripture bar, because on
   `BOTTOM` it sits *above* all of them; clipping against the window rectangles
   as well is the same lookup in the same 72×45 occupancy grid, and every one of
   the five effects is specified to draw only in free space anyway. Measured,
   that buys a 6.0× frame and 60 Hz that actually holds. What it costs:
   - intra-layer ordering on `TOP` is map order, so the surface may land above
     or below Waybar and the caption strip unpredictably — moot only as long as
     the free-region clip is correct, which makes the clip load-bearing for
     appearance and not only for Conky;
   - a bug that draws outside the free region now draws over his work instead
     of under it, which is a worse failure than the `BOTTOM` version's;
   - `ARTWORK-CROSSFADE`'s protection still holds — `background_fade.surface_order()`
     inspects only `layer == 'background'`, so `TOP` is as invisible to it as
     `BOTTOM` was;
   - `DECORATION-PLACEMENT` still requires exclusive zone 0 and
     `FEEDBACK-OSD`/`NOTIFICATION-PLACEMENT` are unaffected, since those are on
     `OVERLAY`.
4. **Do not spend time on blur tuning.** `blur_xray`, a smaller radius, fewer
   passes, disabling shadows and the spec's own `layer_effects { blur disable }`
   were all measured and all do nothing. The 31 ms is damage tracking, not
   dual-Kawase.
5. **The fix that would change this answer is a SceneFX patch, and it is not
   written.** `fx_render_pass_add_optimized_blur` builds its clip from the whole
   node box (`render/fx_renderer/fx_pass.c:1219`) rather than from the frame
   damage, and `wlr_scene_output_build_state` short-circuits the damage
   expansion whenever the damage covers the output. The optimized-blur buffer
   persists between frames, so re-blurring only `damage ⊕ blur_data_calc_size()`
   and copying only that region back would be correct, and would make the cost
   proportional to what actually changed. That is a third patch against a
   library this repository already patches twice, it is plausible rather than
   proven, and nothing in this document assumes it.

Two observations that fall out and are worth recording even though they are not
plank 3:

- **`oldbook-video-background` and `oldbook-youtube` already pay this cost.**
  mpvpaper commits to `--layer bottom` at video frame rate, so the optimized
  blur is invalidated 24-60 times a second for as long as either runs. That is
  not a new risk introduced by this spec; it is an existing one that this
  measurement explains, and it is a reason those two should stay opt-in.
- **Every artwork crossfade already pays it too.** `oldbook-background` is a
  GTK 3 `BACKGROUND`-layer surface whose `add_tick_callback` drives
  `queue_draw()` every frame for the length of a fade, so each crossfade is a
  burst of exactly this. That is legitimate there — the whole backdrop really is
  changing, so a full-output repaint is not waste — and it usefully bounds what
  the machine already tolerates: bursts of about a second.

## 6. Reproducing this

```sh
alpine/verification/scenefx-blur-cost/build-layeranim.sh \
    /path/to/swayfx-*/protocols/wlr-layer-shell-unstable-v1.xml
# then, with layeranim beside measure.py:
python3 alpine/verification/scenefx-blur-cost/measure.py \
    --cases alpine/verification/scenefx-blur-cost/cases-max-rate.json \
    --out /tmp/blurcost-max-rate
python3 alpine/verification/scenefx-blur-cost/measure.py \
    --cases alpine/verification/scenefx-blur-cost/cases-rate-sweep.json \
    --out /tmp/blurcost-rate-sweep
```

`measure.py` spawns `/usr/bin/swayfx` on the headless backend with a private
`XDG_RUNTIME_DIR`, with `SWAYSOCK`, `WAYLAND_DISPLAY` and `DISPLAY` removed from
its environment. It reads `/proc/<compositor>/stat` and
`/sys/class/drm/card1/power/rc6_residency_ms`. Apart from a private
`XDG_RUNTIME_DIR` it creates and deletes under the system temp directory, it
writes nothing outside its `--out` directory. It renders on `/dev/dri/renderD128` (Intel) by default,
which the live session does not use — pointing it at `renderD129` would put a
GPU benchmark on the same device that is drawing the desktop.

### Files

| File | What it is |
| --- | --- |
| `layeranim.c` | The animating layer-shell client: chosen layer, chosen damage rectangle, timer- or frame-callback-driven, empty input region, exclusive zone 0 |
| `build-layeranim.sh` | Compiles it; needs `wayland-scanner` and the layer-shell XML from the SwayFX tarball |
| `measure.py` | The headless harness |
| `live-probe.py` | The measurement on the real panel, for the user to run |
| `cases-max-rate.json`, `results-max-rate.json` | Section 2's first four tables, 18 cases |
| `cases-rate-sweep.json`, `results-rate-sweep.json` | The rate sweep, 12 cases |
| `results-renderer-selector.json` | The `WLR_RENDERER=pixman` control |
| `results-reproduction.json` | The shipped harness re-run end to end after packaging: `BOTTOM` 37.06 ms, `TOP` 6.45 ms, a third independent pair |
| `compositor-bottom.log`, `compositor-top.log` | Trimmed compositor logs: renderer identity, blur config, layer effects, the mapped surface |
| `blurred-bottom-animating.png` | `grim` capture during a `BOTTOM` animation, downscaled to 960×600 |

### Limits of this record

These are observations of one fixture under a loaded host on a GPU the desktop
does not use, at that GPU's minimum clock. They are not a claim about frame
deadlines on eDP-1 and they are not a power measurement — nothing here measured
watts, and the spec's unattributed guess of 2-5 W for a 60 fps fullscreen
composite remains unattributed. The number that would settle the absolute cost
on the machine he actually uses is `live-probe.py`, and only he can run it.
