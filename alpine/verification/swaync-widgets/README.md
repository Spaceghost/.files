# SwayNC control-center widgets

![Control center with media, sound, brightness and quick-action widgets](control-center.png)

Rendered by `alpine/tests/verify_swaync_widgets.py` in a private headless SwayFX
session (pixman renderer) on a private D-Bus session bus with private HOME and
XDG directories, using the checked-in `alpine/desktop/.config/swaync/config.json`
and `style.css`. A fake `org.mpris.MediaPlayer2.ghostradio` player on that bus
supplies the album art card, so the live Pithos session is never touched; the
volume widget reads the live PipeWire Pulse socket read-only when it exists.
Two synthetic notifications are posted before the panel opens. The prev/next
icons render as placeholder glyphs because the private HOME has no icon theme;
the live session uses the Oldbook icon theme.

`evidence.json` records the widget load order from SwayNC's log, the config and
stylesheet hashes, and that no `invalid`, `error`, `critical` or `warning` lines
other than the usual Mesa PCI notice appeared. A headless render does not prove
the live control center: the live check waits for the display to wake.

```sh
python3 alpine/tests/verify_swaync_widgets.py --output /tmp/swaync-widgets
```
