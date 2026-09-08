# Floating decoration verification

The private native SwayFX run passed all 25 checks, with a separate HOME,
configuration, runtime directory and D-Bus. The source SHA-256 values in
`evidence.json` were checked before and after the run. Screenshots contain
synthetic Foot clients only.

A held mouse drag produced intermediate caption positions before settling
flush against the client in 217.3 ms, before releasing the mouse. Both attached
edges reserve no workspace area, including with a 32-pixel exclusive top panel.
The run covers 220×180 floats, fullscreen transitions, pixel checks for tiled
square and floating rounded corners, preferred-edge restoration, a negative
output origin, title middle-click, and focus/workspace/destroy transitions.

Forty focused unit tests passed, including 60/120 Hz animation trajectories,
fullscreen policy across multiple outputs, and persistent IPC recovery.

Reproduce from the checkout root:

```sh
python3 -m unittest discover -s alpine/tests -p 'test_decoration*.py' -v
python3 alpine/tests/verify_decoration_attachment.py --output /tmp/decoration-attachment-new
```

The native run uses one headless output. Simultaneous physical multi-output and
mixed-refresh rendering were not exercised. Existing GTK/GI deprecation notices
remain; private runtime logs are retained under `/tmp/oldbook-decoration-attachment-native6/`.
