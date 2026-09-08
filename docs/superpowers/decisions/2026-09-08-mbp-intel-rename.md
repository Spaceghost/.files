# Rename the desktop identity from oldbook to mbp-intel

The user asks for the `oldbook` references to become `mbp-intel`. That string is
the desktop's own identity: it names 48 HOME helpers, the shared Python package,
the runtime state, share, config and library directories, the icon theme, the
Waybar palette colors, the nftables table, the drop-down application IDs, the
environment variables, the packaged Alpine artifacts and the prose in every
guide. Renaming it partially would leave the desktop referring to two machines,
so the identity is replaced everywhere it is a live reference.

Three forms cannot take a hyphen. Python identifiers and module names use
`mbp_intel`, so the shared package directory is `.local/lib/mbp_intel` and its
imports read `from mbp_intel.app_identity import ...`. Environment variables use
`MBP_INTEL_`, keeping the existing `OLDBOOK_` semantics unchanged. GTK CSS color
names use `mbp_intel_workspace_active` and `mbp_intel_workspace_secondary`.
Executables, directories, application IDs and file names take the hyphenated
`mbp-intel`, and the capitalized prose noun becomes `MBP Intel`.

Recorded history is not rewritten. `alpine/verification/`, `alpine/archive/`,
`alpine/packages/locks/`, `alpine/packages/world`, `alpine/packages/current-lock`
and the installed OpenSnitch rule copies under
`alpine/packages/1password/firewall/rules/` state what was actually built,
installed and observed under the old name. Editing them would falsify evidence
whose value is that it matches artifacts and hashes on disk. The FEATURES table
row naming the superseded `oldbook-desktop` package is preserved for the same
reason. The Fossil branch stays `alpine-oldbook`: it is the identity the GitHub
mirror pushes to, and renaming it would orphan that mirror and every other
session committing to it.

Verification covers source correctness only. The full unit suite, Python and
POSIX shell syntax over every renamed file, JSON parsing, `sway --validate` and
the feature-check index all run against a clean checkout of the branch tip.

This check-in does not migrate the running machine. The live desktop still has
`oldbook` HOME symlinks, `~/.local/{state,share,config,lib}/oldbook` runtime
data, the `Oldbook-Gruvbox` icon-theme setting, the root `sway` wrapper and
wayland session entry, the `inet oldbook` firewall table, `/etc/oldbook`,
`/var/lib/oldbook`, the installed `oldbook-waybar-art` and
`oldbook-radio-runtime` packages and the `oldbook` hostname. Activation requires
moving that personal data, redeploying HOME, removing the stale symlinks,
reinstalling the desktop entrypoint, rebuilding and reinstalling both packages,
and reactivating the firewall. Doing that mid-session would break the running
compositor and the agent sessions attached to it, so it is deliberately left as
a separate, user-authorized migration.
