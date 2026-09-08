# Decoration hover handoffs

The native regression first failed on the original daemon: a hover from a
420-pixel window to a 620-pixel window produced intermediate position/width
adjustments for 135 ms. `before.json` preserves the sampled failure and source
hashes. Snapping the position alone also exposed one frame with the old width.

The final daemon passed all 28 native attachment checks and 41 decoration unit
tests. Nine pointer handoffs included six rapid alternations requested every
80 ms. Every visible sampled caption had one complete target rectangle, with
at most one caption surface. After rapid switching, the final target settled
correctly. A held drag still rendered intermediate positions and settled flush
in 132.1 ms, before releasing the pointer.

The three settled hover cases first sampled the complete new target after
106.75–159.31 ms under this run's load. Two handoffs sampled an unmapped interval;
the surrounding observations bound those intervals to 19.81 and 30.78 ms.
Sampling may miss shorter gaps or frames; these are headless compositor
measurements, not physical panel scanout guarantees. Screenshot fixtures contain
only synthetic terminals.

`evidence.json` includes source hashes, all geometry samples and native checks.
`activation.json` records the scoped live daemon restart, one caption on eDP-1
and the unchanged saved appearance hash. The first activation timed out waiting
for the live compositor's initial configure; a targeted helper retry succeeded
after Sway became responsive, without restarting the compositor or bar.
Complete logs, failed attempts and the
passive frame smoke check are retained in
`~/.local/state/oldbook/decoration-hover/`. The frame check recorded ticks,
draws and after-paint callbacks, including 13 startup frames, with no repeated
resize requests while moving.

Reproduce from the checkout root:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_decoration*.py' -v
python3 alpine/tests/verify_decoration_attachment.py --output /tmp/decoration-hover-new
```

The test uses a private D-Bus, HOME, XDG directories, SwayFX output and pointer.
It does not change the live compositor configuration or move the user's windows.
