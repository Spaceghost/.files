# Restore personal tmux controls across themes

The themed configuration skipped the historical root `.tmux.conf` because it
contains TPM declarations. A fresh tmux server therefore used Ctrl+B even though
the historical config specifies Ctrl+A.

Every theme now sources `~/.config/tmux/mbp-intel.conf`, deployed from the Alpine
desktop overlay. This file carries the historical native prefix, splits, Vim
navigation/resizing and copy controls, numbering, scrollback, mouse, clipboard,
focus and activity settings. Theme colors, status formats and pane-title
forwarding remain in each theme. The renderer reads the desktop template, so
future themes inherit the include. Existing generated local profiles were also
updated. A base overlay deployment supplies the shared file; upgrading an
existing home needs only `deploy-home --only .config/tmux/mbp-intel.conf`.

The historical minus binding was assigned twice; the final action, resize down,
is preserved. The `s` binding provides top/bottom splitting. Existing default
arrow, split and help bindings remain available. Plugin bootstrap and historical
machine-specific helper commands are not imported.

Validation: reproduced Ctrl+B in an isolated server before the change. After
the change, 25 shipped/rendered configurations loaded twice under a disposable
deployed HOME with tmux 3.7c. Verified Ctrl+A, split/navigation/resize bindings,
new windows and panes starting at 1, vi mode, mouse, history limit, title
forwarding and themed status styles. All 18 deployment/recovery tests and three
complete-theme tests passed. No shell scripts changed.

Deployed the shared file and reloaded the running server. All three remaining
live sessions report Ctrl+A; pane process IDs and status colors/formats match
before and after reload. Runtime evidence is local in
`~/.local/state/mbp-intel/tmux-preferences/{before,isolated,live}.json`.
The scrollback limit applies to newly created panes. A logout/login and physical
keyboard interaction were not exercised.

For immediate prefix recovery, run `tmux set-option -g prefix C-b`,
`tmux bind-key C-b send-prefix`, and `tmux unbind-key C-a`.
For persistent rollback, restore the previous desktop and tracked theme tmux
configs, update generated profiles from the restored template, and roll back
the shared-file deployment with
`alpine/bin/deploy-home --rollback ~/.local/state/mbp-intel/backups/1788832442599996146`.
Already-running servers retain other loaded controls until explicitly reset or
restarted after their sessions have been saved.
