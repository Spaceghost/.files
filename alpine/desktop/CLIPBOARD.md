# Desktop clipboard and history

Use **Super+Shift+V** to search clipboard history. Choose an entry with Enter,
then paste normally in the destination. Escape leaves the current clipboard
untouched. Text and images are retained byte for byte, including newlines.
The menu also offers **Delete an entry** and **Clear history**; clearing from
the menu asks once before removing the history. **Super+Ctrl+Shift+V** opens
the delete picker directly. Super+V still selects vertical splits.

In Foot and Ghostty, selecting terminal text copies it to the regular
clipboard as well as the primary selection. Use Ctrl+Shift+C / Ctrl+Shift+V
for terminal copy/paste and the application's normal Ctrl+C / Ctrl+V in GUI
apps. Hold Shift while selecting in Foot to bypass an application's mouse
handling. In tmux, Ctrl+A then [ enters copy mode; v starts a selection, y
copies while staying in copy mode, and Enter copies and exits. Mouse selection
in tmux also copies. Neovim's unnamedplus clipboard uses wl-clipboard.
Screenshots copy PNG data before opening the annotation tool.

`oldbook-clipboard daemon` runs two wl-paste watchers for text and images and
wl-clip-persist for the regular clipboard. A per-Wayland-display flock makes
session reloads safe. The persistence service preserves all offered formats,
including file-manager MIME types, and keeps a copy after the source app exits.
It leaves the primary selection lifecycle alone. Incomplete reads and offers
larger than 32 MiB remain with the source app. History stores up to 200 items,
with an 8 MiB per-item limit, under
`~/.local/state/oldbook/clipboard/history.db` (private directory and database).
Copies marked sensitive with the password-manager MIME hint are neither
archived nor retained by the persistence service. Unmarked copies are ordinary
history entries; delete them through the menu when necessary.

CLI: `oldbook-clipboard list`, `pick`, `delete`, `clear`, `copy` (text on stdin),
and `paste` (text on stdout without an added newline). Plain `cliphist` uses
its own default database; use this helper to manage the desktop history.

## Deployment, verification, and recovery

Install `cliphist@testing` and `wl-clip-persist@testing` from the tagged HTTPS
Alpine testing repository. Their exact signed APKs are archived in Fossil;
see `alpine/packages/clipboard/manifest.json` for identities and hashes.
Deploy `.local/bin/oldbook-clipboard`, `.local/bin/oldbook-session`,
`.local/bin/oldbook-screenshot`, `.config/tmux/oldbook.conf`, and
`.config/sway/local.d/clipboard.conf` using `alpine/bin/deploy-home --only`.
The normal session starter owns the daemon. Existing tmux servers can source
`~/.config/tmux/oldbook.conf` directly. Existing Foot windows keep their startup
configuration: reopen standalone Foot windows to enable mouse auto-copy;
explicit Ctrl+Shift+C and the live tmux fix work without closing them.

Tests: `python3 -m unittest discover -s alpine/tests -p test_clipboard.py -v`.
The contained runtime check in `alpine/tests/verify_clipboard.py` uses a separate
headless Sway/XWayland session and synthetic contents. It records results and
a screenshot under `alpine/verification/clipboard/`; it never reads or writes
the active desktop clipboard.

To recover, restore the exact files from the deployment journal and revert
this change's shared/theme terminal options. Terminate only the
`oldbook-clipboard daemon` process for the active display; it stops its children.
Remove its session-start entry to keep it stopped, and reload the tmux controls
and Sway shortcut configuration. Leave the private history database intact
unless its removal is intended. Package removal is optional.

Upstream references:
- https://github.com/sentriz/cliphist/tree/v0.7.0
- https://github.com/Linus789/wl-clip-persist
- https://codeberg.org/dnkl/foot
- https://ghostty.org/docs/config/reference#copy-on-select
