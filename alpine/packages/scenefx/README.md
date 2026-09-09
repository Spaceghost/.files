# SceneFX for Oldbook

SwayFX 0.6 owns no blur code of its own. Every blur symbol in `/usr/bin/swayfx`
is undefined (`U`) and resolved at load time from `/usr/lib/libscenefx-0.5.so`:
`blur_data_get_default`, `wlr_scene_set_blur_radius`, `wlr_scene_blur_create`,
`fx_render_pass_add_blur`, and the rest. The scene graph, the damage tracking
and the whole blur artifact-compensation pass live in SceneFX, so a blur bug is
fixed here rather than in the compositor.

This package is Alpine `community/scenefx` 0.5-r0 rebuilt from the same pinned
tarball with two upstream fixes that landed after the 0.5 tag. It keeps the
same `pkgver`, so the only thing apk sees is the newer revision, and it
replaces the official package rather than living beside it — there is one
`libscenefx-0.5.so` and the installed SwayFX links to it by soname.

## The blur that smears around the pointer

Transparent windows — Foot most visibly — grew smeared square patches that
followed the mouse. The squares are damage rectangles, and this is what puts
stale content in them.

`screen-corners.patch` in the SwayFX package calls
`wlr_output_lock_software_cursors(wlr_output, true)`, because the black output
mask has to be composited above the cursor. This desktop therefore runs a
**software** cursor: the pointer is drawn into the output buffer by
`wlr_output_add_software_cursors_to_render_pass()`, and every pointer move
damages a cursor-sized rectangle wherever the pointer was and wherever it now
is.

Dual-Kawase blur samples well outside the pixels it writes. SceneFX measures
that reach as `blur_data_calc_size() = 2^(num_passes + 1) * radius`; the
desktop's `blur_passes 1`, `blur_radius 4` make it 16 buffer pixels. A blur node
re-rendered inside a small damage rectangle reads 16 pixels of *neighbouring*
framebuffer, and outside the damage region the framebuffer still holds this
buffer's previous composite — already-blurred content and an older cursor. Blur
the blur and you get the smear.

SceneFX 0.5 does know this. `wlr_scene_output_build_state()` expands the frame
damage by the blur footprint for every blur node about to be drawn
(`apply_blur_region`), saves the surrounding padding ring, renders, and pastes
the ring back afterwards, so the blur always samples freshly rendered pixels.
**The compensation was not missing — it was being skipped.** Just above it sits
a shortcut:

```c
const bool full_damage =
	original_damage.extents.x2 - original_damage.extents.x1 >= output->width
	&& original_damage.extents.y2 - original_damage.extents.y1 >= output->height;
```

`extents` is the *bounding box* of the damage region, not its area. Two small
rectangles in opposite corners of the screen give a bounding box the size of the
output while almost nothing is actually damaged. A cursor rectangle plus any
other repaint — the Waybar clock, a Conky card, the pointer's own previous
position after a fast diagonal flick — is exactly that shape. `full_damage` then
reads true, SceneFX concludes the whole output is being redrawn anyway, skips
the damage expansion entirely, and the blur nodes re-sample stale framebuffer.

Both observations fit. `blur_xray enable` stops it because an xray blur node
takes the `should_only_blur_bottom_layer` early return in
`should_blur_node_extend_damage()`: it reads the pre-rendered optimized-blur
backdrop and never re-samples the live framebuffer, so the skipped compensation
costs it nothing. Foot's `damage-whole-window=yes` does not stop it because the
damage that inflates the bounding box is the *cursor's*, not the client's.

## The patches

Applied in this order:

| Patch | Origin |
| --- | --- |
| `add-missing-include-for__always_inline.patch` | Alpine aports, carried by the official package: musl needs `linux/stddef.h` in `clipped_region.h`. |
| `blur-damage-output-clip.patch` | Upstream [`06fb6d8`](https://github.com/wlrfx/scenefx/commit/06fb6d8dac68485d1cac075baa60a15408a84666) |
| `blur-damage-coverage.patch` | Upstream [`3606f3d`](https://github.com/wlrfx/scenefx/commit/3606f3d3bb4bb97e13228adc5190bf57fc687c88) |

`blur-damage-coverage.patch` is the fix. It replaces the bounding-box test with
`pixman_region32_contains_rectangle(&original_damage, &output_box) ==
PIXMAN_REGION_IN`, which asks whether the damage region actually *covers* the
output. Scattered small rectangles no longer masquerade as a full repaint, so
the damage expansion runs whenever any blur node is partially damaged and the
blur can never sample a pixel that was not re-rendered this frame. The output
box comes from the buffer rather than the output, which is also the correct
space: the damage has already been converted to buffer coordinates.

`blur-damage-output-clip.patch` is a consequence of the first. `node->visible`
is in layout coordinates, so a node straddling two outputs contributes negative
rectangles to `output_state->damage`, and wlroots forwards that state to
`ext-image-copy-capture`, where a negative origin is a fatal protocol error —
any monitor screencast through `xdg-desktop-portal-wlr` dies. On 0.5 that path
was reached only on the frames where compensation happened to run; with the
coverage fix it runs on nearly every frame with a blurred window on screen, so
the clip is no longer optional.

Neither patch changes a type, a struct or an exported signature, so the rebuilt
library stays ABI-compatible with the installed `swayfx-0.6-r4`.

## Cost

The compensation is not free: it now runs on most frames instead of
intermittently. What it costs is two clipped texture blits over the padding
ring, which at `blur_passes 1` / `blur_radius 4` is a 16-buffer-pixel band
around each blurred window — thin, and far cheaper than the whole-output
repaint the old shortcut wrongly assumed was already happening. `MOTION`'s
frame-rate target has not been measured against this build; see the limits in
`verification.json`.

## Build

Packages are built on a build host, never on this laptop:

```sh
alpine/bin/remote-build build --host bak scenefx
```

The recipe is `options="!net"`, so the pinned tarball travels beside it:
`remote-build` exports it from this Fossil repository's unversioned storage by
its own SHA-256, which is the checksum `abuild` then verifies. The build host
signs with a throwaway key and the signature is replaced here; the private key
never leaves this machine.

`build-offline` is the recovery path for a machine that has no build host. It
runs `abuild rootbld` against an explicitly exported source and refuses to start
unless `OLDBOOK_ALLOW_LOCAL_BUILD=1` says the fans are a deliberate choice:

```sh
fossil uv export sha256/0fa8ecca0e310f813efd052624c5ed7d9153d6a0fdead5cc957d34c07f9a86c6/scenefx-0.5.tar.gz /tmp/scenefx-0.5.tar.gz
OLDBOOK_ALLOW_LOCAL_BUILD=1 alpine/packages/scenefx/build-offline \
    --source /tmp/scenefx-0.5.tar.gz --work /tmp/scenefx-build
```

`manifest.json` records the source and patch hashes, the upstream commits the
patches come from, and every deviation from the aports recipe.

## Verification

`verification.json` has the record. In short: two independent builds on `bak`,
in separate ephemeral containers, produced byte-identical signed APKs for all
three packages; all of them pass `apk verify`; `abuild` applied every patch with
no fuzz and no offset; the rebuilt `libscenefx-0.5.so` exports exactly the same symbol set as the 0.5-r0 library it
replaces, with the same soname and the same `DT_NEEDED` list; the only new
undefined symbol in the whole library is `pixman_region32_contains_rectangle`,
which is the fix and nothing else; all 73 SceneFX symbols `/usr/bin/swayfx`
imports are still resolved; and the installed SwayFX runs headlessly against the
rebuilt library on `renderD129`, loading scenefx 0.5.0, initialising the FX
shaders and drawing a blurred, rounded, shadowed frame.

What is *not* verified is the symptom. Proving the smear is gone needs a live
session with a software cursor, a blurred transparent window and a moving
pointer. The headless backend has no cursor, and the running compositor still
has the old library mapped.

## Installing is a separate decision

This package replaces a shared library underneath a **running** compositor.
Nothing here installs it.

```sh
cd ~/.cache/oldbook-apks && apk add ./scenefx-0.5-r1.apk ./scenefx-dev-0.5-r1.apk
```

`apk add --simulate` on those two files resolves to exactly two upgrades,
`scenefx 0.5-r0 -> 0.5-r1` and `scenefx-dev 0.5-r0 -> 0.5-r1`, and touches
nothing else in the 1128-package closure. Both are named together because
`scenefx-dev` pins `scenefx=$pkgver-r$pkgrel`; installing one alone would pull
the other back from Alpine community. `scenefx-doc` is built and archived but is
not currently installed, so it is not in the command.

What that does and what it risks:

- The file at `/usr/lib/libscenefx-0.5.so` is replaced. SwayFX is running right
  now and has that library mapped, so it keeps the old inode: the current
  session neither changes nor gains the fix, and the smear stops at the next
  graphical login. Do not restart the compositor to hurry it — that ends the
  session and every client in it.
- `swaymsg reload` will not help either. Reloading re-reads the configuration in
  the same process; only a new process picks up a new library.
- Anything else linking `libscenefx-0.5.so` picks up the new code at its next
  start. On this machine that is SwayFX alone.
- Keeping `scenefx` and `scenefx-dev` at the same revision matters for the next
  SwayFX rebuild, which compiles against the headers in `-dev`. A mismatch there
  is how a hard-to-diagnose crash starts.
- The recovery is `apk add scenefx=0.5-r0 scenefx-dev=0.5-r0` from Alpine
  community, or the archived official APKs in this repository, followed by a new
  login. `OLDBOOK_STOCK_SWAY=1 sway` starts the stock compositor, which does not
  link SceneFX at all, if a login ever fails.

Upstream: [SceneFX 0.5](https://github.com/wlrfx/scenefx/releases/tag/0.5),
[Alpine community/scenefx](https://gitlab.alpinelinux.org/alpine/aports/-/tree/master/community/scenefx).
