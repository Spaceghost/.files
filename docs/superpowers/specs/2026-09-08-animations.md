# Window and workspace animations — 2026-09-08

## What

SwayFX r4 carries `window-animations.patch`, which gives the compositor a
horizontal workspace slide, a duration per animation kind, and a single command
that switches every animation off.

New configuration commands, documented in the packaged `sway.5.scd`:

| Command | Meaning |
| --- | --- |
| `animations enable\|disable\|toggle` | Switches all animation off without losing the durations |
| `animation_open_ms <value>` | Window opening; 0 uses `animation_duration_ms` |
| `animation_close_ms <value>` | Window closing; 0 uses `animation_duration_ms` |
| `animation_move_ms <value>` | Layout moves and resizes; 0 uses `animation_duration_ms` |
| `animation_workspace_ms <value>` | Workspace switch; 0 uses `animation_duration_ms` |
| `animation_workspace_style slide\|fade\|both` | How a switch is drawn; `slide` is the default |

The desktop's values live in `alpine/desktop/.config/swayfx/animations.conf`:
160 ms open, 130 ms close, 140 ms move, 220 ms workspace, sliding.

## Why this shape

SwayFX 0.6 already animated more than it looked like. Reading
`sway/animation_manager.c` and `sway/desktop/transaction.c` showed that opening
windows pop in from 0.8 scale while fading up, closing windows pop out from a
saved buffer, and layout moves and resizes already tween. What was missing was
worth building:

- A workspace switch only **crossfaded**. Sliding is the motion that actually
  tells you which way you moved through the workspaces.
- There was **one** duration for everything, so a snappy window open forced an
  equally snappy workspace switch, and the only way to disable animation was to
  set that duration to zero and forget what it had been.

So the patch adds those two things rather than reimplementing what upstream
already does well.

### Per-kind durations

`struct animation` gained `duration_ms` and its own `progress_delta`; the tick
loop steps each animation by its own delta instead of one shared value. That is
the whole mechanism, and it also means `refresh_animation_manager_timing` has to
re-derive the step of everything already in flight when a duration changes or an
output's refresh rate changes, which it now does.

`animation_kind_duration()` resolves a kind: its own value when set, otherwise
the shared `animation_duration_ms`, and zero whenever `animations` is disabled.
Zero takes the instant path, so a disabled kind schedules nothing and requests no
frame. `get_animated_value` no longer consults the global duration at all; an
uninitialised animation returns the target, which is the same answer with fewer
assumptions.

### The slide

`arrange_output` sets a start and end offset on both workspaces and runs them
through `workspace_slide_update_callback`. The arriving workspace enters from
the side its number lies on; names that do not begin with a digit sort to the
right of numbered ones, which keeps the direction stable for `10: Strata`.

Two details took care:

- **Floating windows are not in the workspace tree.** They are reparented to
  `root->layers.floating` and positioned in layout coordinates, so the slide
  cannot simply offset one scene node. Each floating container records the
  position it really sits at on the first tick of a slide, keyed by the
  workspace that captured it, and is drawn at that base plus the current offset.
  Keying on the workspace rather than a flag means a window that changes
  workspace mid-slide re-captures instead of drifting from a stale base.
- **An interrupted slide never runs its completion callback.** Switching
  workspaces again mid-animation would otherwise leave a stale offset and put
  every window on that workspace permanently in the wrong place. `arrange_output`
  settles both workspaces back to their real coordinates before starting the
  next slide.

## What was deliberately left out

**Fullscreen enter and leave are not animated.** Fullscreen containers are
arranged through `arrange_fullscreen`, a separate path that writes the output
rect straight into the scene graph, and `anim_update_callback` returns early for
them. Animating it means routing fullscreen through the same animation state as
ordinary containers. That is a real change to the path used by video, games and
screen sharing, on a machine that is a daily driver, and the payoff is one
transition. The sound subset ships instead; the early return and the
`is_ws_switch` fullscreen exclusion are untouched.

## Verification

Two isolated builds with networking disabled produced byte-identical signed
APKs, `750a7e28df64d9b26a025f6244aaed6485937c2f8910e694925a820a7e61f378`;
`apk verify` passed. `verify-window-animations` ran the packaged binary in a
private headless session and passed all nine checks, including the colour proof
that a slide separates the two workspaces horizontally while a fade does not,
and that a disabled switch is instant. Idle cost with animations enabled and
nothing moving measured 0.0% of a core over five seconds. Sixteen unit tests
cover the configuration bounds and the launcher probe. Evidence:
`alpine/verification/swayfx-animations/`.

Not verified: the physical frame rate on the panel, and the look of the slide
alongside blur and shadows, which the software renderer cannot show. The
animations begin at the next graphical login.

## Activation, and why it is indirect

The running compositor is the previous build, and it rejects an unknown command
by refusing the whole configuration. Putting the new commands in `effects.conf`
would break the live session the moment anything reloaded it.

So `animations.conf` is a separate file that nothing includes by default, and
`oldbook-sway` probes the installed compositor with
`swayfx --validate` before each login. When the probe passes it writes a small
session configuration into `$XDG_RUNTIME_DIR` that includes the usual config and
then the animations, and starts the compositor from that. When it fails, the
launcher starts exactly as it did before. The versioned configuration is never
rewritten, and a reload re-reads whichever file the probe chose.

## Rollback

`doas apk add` the archived r3 artifact
(`sha256/30025561ef1e7cef8d95c51e75e2b08c94cc3411d857071005ae427977b4fa8f/swayfx-0.6-r3.apk`)
and log in again. Short of that, `animations disable` at runtime or in
`animations.conf` stops all motion while keeping the binary, and deleting
`animations.conf` makes the launcher's probe fall back to the previous
behaviour on its own.
