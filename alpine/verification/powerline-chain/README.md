# Powerline status chain evidence

Rendered on 2026-09-13 by `tests/verify_powerline_chain.py` in a private
headless SwayFX session (2880×160 at scale 2) with the real Waybar, each theme's
own `config.jsonc` and `style.css`, and the accent file `oldbook-palette` writes
for gruvbox's declared accent. Still labels stand in for every helper-driven
module, so no helper ran, and the live session was never captured: it was locked
with its panel powered off.

| Capture | State |
| --- | --- |
| `before.png` | gruvbox-dark as it stood live before the fix, rendered by the same harness: the chips never painted, because `#group-telemetry` names nothing Waybar draws, and each glyph separator showed as a strip. |
| `gruvbox-dark.png` | One continuous chain: flush chips joined by drawn rounded caps, closing over the island. |
| `catppuccin-mocha.png` | The same chain in Catppuccin's tones. |
| `monochrome-test.png` | Alternating white and black chips, with black text on the white ones. |

`evidence.json` records the source hashes of every stylesheet and config the
run read, the verifier's own hash, and a cleanup that left no private process
behind. Not recorded here: the panel itself, hover, and a drawer group opened
by the pointer.
