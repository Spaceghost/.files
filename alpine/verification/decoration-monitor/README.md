# Skip the system-monitor drop-down

The caption skips exact app ID `com.oldbook.monitor` alongside the current and
legacy console IDs. Opening either drop-down retains the preceding ordinary
window's caption geometry, title and action target.

`native.json` records six passing checks in a private headless SwayFX session.
Across 150 samples during monitor show/hide over ordinary Foot and Ghostty
windows, the caption target and rectangle stayed unchanged, with one caption
surface throughout. The monitor fixture is Foot with the production monitor
app ID and synthetic text; the normal Ghostty control uses the actual binary
and its default app ID. The two screenshots show the retained captions.

The existing unit cases were extended to include monitor focus and both
fullscreen modes. Three monitor subtests failed before the source change;
all 47 decoration tests and Python compilation passed afterward:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_decoration*.py' -v
python3 -m py_compile alpine/desktop/.local/lib/oldbook/decoration.py
```

`activation.json` records a targeted restart of the live decoration daemon,
matching source hashes, one caption per active output, matching placement/action
targets, and unchanged appearance settings. This change does not alter the
console or monitor shortcuts. Physical keypress input is outside this caption
check.

Recovery: remove only `com.oldbook.monitor` from `IGNORED_CAPTION_APPS` in
`decoration.py` and restart the decoration daemon.
