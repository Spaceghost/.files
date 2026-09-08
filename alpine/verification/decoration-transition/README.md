# Immediate tile/float decoration transitions

The previous mode-change crossfade left two caption surfaces visible for about
220 ms. Replacement captions now map fully opaque, at their final placement.
Configured background transparency still applies.

`timing.json` compares isolated native runs before and after the fix:

| Transition | Before stable attachment | After stable attachment |
| --- | ---: | ---: |
| Plain floating enable | 231 ms | 22 ms |
| Centered resize from tiled | 305 ms | 91 ms |

Both fixed transitions had zero overlapping caption samples, full opacity on
map, and flush final attachment. `settled.png` shows the centered resize result.
These are headless compositor and GTK observations under the current host
workload; they do not measure physical display scanout.

`attachment.json` records all 28 passing native regression checks, including
drag animation, focus handoffs, fullscreen, tile/float controls, output origins,
and workspace changes. The 41 decoration unit tests and Python compilation also
passed. `activation.json` confirms the deployed source hash, one live helper,
one caption per active output, and preserved appearance settings after restart.

Reproduce from the checkout, using a new output directory for each run:

```sh
python3 alpine/tests/verify_decoration_transition.py --output /tmp/transition-check
python3 alpine/tests/verify_decoration_attachment.py --output /tmp/attachment-check
python3 -m unittest discover -s alpine/tests -p 'test_decoration*.py' -v
```

The transition verifier takes a source snapshot, starts private headless SwayFX,
and records GTK callbacks plus persistent IPC samples. It asserts full opacity
on map, zero overlapping captions, and final flush geometry. It retains raw
samples and logs in its output directory. The original comparison traces remain
in `/tmp/decoration-transition-before` and `/tmp/decoration-transition-after`;
the broader run is in `/tmp/decoration-mode-attachment`.

Recovery: restore only `alpine/desktop/.local/bin/oldbook-decoration` from the
parent of this check-in and restart only the decoration daemon. Appearance
settings are separate and need no restoration.
