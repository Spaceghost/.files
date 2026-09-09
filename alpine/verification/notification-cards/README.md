# Notification cards

`cards.png` is four states rendered from the real stylesheet through swaync's
own widget classes: normal at rest, normal hovered, critical, low.

Render it with:

```sh
python3 alpine/tests/render_notifications.py \
    alpine/desktop/.config/swaync/style.css /tmp/cards.png
```

Why this exists. `swaync-client --reload-css` reports success even when GTK has
silently dropped declarations it could not parse, so a stylesheet can look
accepted and do nothing. Worse, two rounds of this design were written without
anyone looking at the result: the first bloomed the accent 26 pixels into the
card and turned every notification olive, which reads as a stain rather than as
light, and no amount of reasoning about the CSS revealed it. Rendering takes a
second and settles it.

The loader deliberately drops declarations a plain `GtkCssProvider` rejects and
prints them: swaync parses `:root` custom properties and `filter: blur()`
itself, and neither is GTK CSS. Anything else it reports is a real error.
