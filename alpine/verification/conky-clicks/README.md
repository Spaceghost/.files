# Native Conky card clicks

`alpine/tests/verify_conky_clicks.py` drives a private headless Sway seat with
real Wayland pointer events against the Scripture, Witness and journal cards.

- `before.png`, `after.png`: the desktop before and after one left-click on each
  card; only the clicked card's Conky process is replaced and redrawn.
- `returned.png`: after a right-click on the Scripture card, which returned the
  passage from John 3:17 to John 3:16 (`right_click_returned_reference`).
- `floating-cover.png`: tiled and floating application windows keep their own
  input above the cards.
- `native.json`: timings and outcomes of the latest run; `native.log`: client output.

Rerun from the checkout root: `python3 alpine/tests/verify_conky_clicks.py`.
It writes here, needs sway, conky and grim, and never touches the live desktop.
