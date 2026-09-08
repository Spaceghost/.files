# Theme creation notification

The new-theme generation path sends one completion notification after saving
the image/sidecar and attempting its local checkpoint and any requested desktop
activation. The notice contains the real theme name and the saved painting,
with a readable body preview and a thumbnail fallback. Saved-only creation,
failed desktop activation and pending checkpoints are described accurately.
Image-generation failures never show a completion preview. Existing checkpoint
repair and image retry behavior are unchanged.

`notification.png` shows the real SwayNC 0.12.6 rendering in a private headless
SwayFX session. The theme and painting labels are synthetic; the image is the
existing gallery painting `delaware.png`. Both ampersands and angle brackets
render as text, the full theme name wraps in the body, and the painting appears
below it. The summary can ellipsize according to SwayNC's existing width.

The harness used its own D-Bus server with service activation disabled, checked
that the notification bus owner matched its spawned SwayNC PID, and observed
exactly one notification. No image generation, live notification, gallery
mutation, theme switch or compositor restart was performed. `evidence.json`
records the source/image hashes. `unit-tests.log` covers 27 fixture tests,
including creation success/failure, notification argument safety, markup and
existing themed generation behavior.

Reproduce from the checkout:

```sh
PYTHONPATH=alpine/tests python3 -B -m unittest test_theme_completion_notification test_new_themes test_themed_artwork -v
python3 -B alpine/tests/verify_theme_notification.py --output /tmp/theme-notification-preview
```

The deployed `oldbook-wallpaper` resolves to this checkout and launches
`alpine/wallpapers/generate.py` for each request. Future new-theme requests use
the notification immediately; already-running Python jobs keep their loaded
code. Recovery is to restore the prior generator revision. No service/config
reload is needed. Notifications respect the existing desktop Do Not Disturb
setting and require a running notification service.

The wrapper uses the standard [image-path hint](https://specifications.freedesktop.org/notification/latest/hints.html)
and [body image markup](https://specifications.freedesktop.org/notification/latest/markup.html).
The installed SwayNC version's [body-image renderer](https://github.com/ErikReider/SwayNotificationCenter/blob/v0.12.6/src/notification/notification.vala)
supports this local-file URI preview.
