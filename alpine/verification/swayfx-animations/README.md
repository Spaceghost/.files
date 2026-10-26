# Window and workspace animations

![A marked console attached to the top edge with square top and rounded bottom corners](frames/dropdown-corners.png)

SwayFX r5 adds a reversible Quake-style drop-down reveal, grows windows into
place as they open, and supports both workspace slides and fades with a separate
duration for each kind. `evidence.json` and the 60 frames here
come from `alpine/packages/swayfx/verify-window-animations`, which runs the
packaged binary in a private headless session and never touches the live
desktop.

## How the frames prove it

Telling a slide from a crossfade needs more than a screenshot, so the check is
colour based. Workspace 1 holds a solid red terminal, workspace 2 a solid green
one, and the harness grabs a burst of frames through the switch. Three
signatures separate the three behaviours:

- **slide** shows both colours at once, sitting in different halves of the
  output. Across `frames/slide-*.png` the red mean column walks 622 → 2 while
  green walks 1262 → 642, staying roughly one screen width apart the whole way:
  one workspace leaving as the other arrives.
- **fade** shows the two colours mixed over the same pixels, never separated
  horizontally.
- **disabled** never shows both colours in any frame; the switch is instant.

`frames/open-*.png` track a window opening. Its bounding box grows 1084 → 1252
pixels over the capture, which is the pop-in scale ramp arriving at its settled
size.

`frames/dropdown-reveal-*.png` move the console's bottom edge 12 → 492 pixels
downward. The dismissal moves 468 → 0 upward, and an interrupted dismissal
reverses 24 → 492 without parking the terminal. In the settled corner frame,
the first red pixel begins 1 pixel from the top-left edge but 19 pixels from the
bottom-left edge: square on top, rounded only on the bottom.

## Results

All thirteen checks passed on the packaged r5 binary
(`c861b8d1ff07aca0f82cb8d167a22ec850e3479498ab462cf744e19d97eeb695`). With
animations enabled and nothing moving, the compositor used **0.0%** of a core
over five seconds: the tick list is empty, so no frame is requested at all.

```sh
alpine/packages/swayfx/verify-window-animations \
    --binary /usr/bin/swayfx --output /tmp/swayfx-animation-test
```

## Limits

The headless backend uses the pixman software renderer, so these frames prove
ordering, geometry and the scene graph settling correctly. They do not prove the
physical frame rate on the panel, and they show no blur or shadows, which need
the GLES2 renderer. Fullscreen enter and leave are deliberately not animated;
the [r5 design](../../../docs/superpowers/specs/2026-10-26-quake-dropdown-motion-design.md)
explains why. The animations run only after the next graphical login, because a
compositor cannot replace its own executable.
