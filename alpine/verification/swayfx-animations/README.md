# Window and workspace animations

![Two workspaces caught mid-slide: red leaving to the left, green arriving from the right](frames/slide-01.png)

SwayFX r4 slides workspaces sideways, grows windows into place as they open and
shrinks them away as they close, with a separate duration for each kind and one
command that switches the whole lot off. `evidence.json` and the 32 frames here
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

## Results

All nine checks passed on the packaged r4 binary
(`b8cef3c864cc92cd4e37f1868cff36a95e5c0a03478aff87fe0d454ba729eed4`). With
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
`docs/superpowers/specs/2026-09-08-animations.md` explains why. The animations
run only after the next graphical login, because a compositor cannot replace its
own executable.
