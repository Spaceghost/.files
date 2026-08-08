# .files

[![check](https://github.com/Spaceghost/.files/actions/workflows/check.yml/badge.svg?branch=base)](https://github.com/Spaceghost/.files/actions/workflows/check.yml)

A small, sharp Unix environment for macOS and Linux.

No dotfile framework, no startup-time downloads, and no config that needs a
plugin manager just to open a shell. The interesting bits are plain files that
remain useful on a fresh machine.

## Install

```sh
git clone https://github.com/Spaceghost/.files.git ~/.files
cd ~/.files
./install --dry-run
./install
```

The installer only creates symlinks. Existing files are moved to a timestamped
backup under `${XDG_STATE_HOME:-~/.local/state}/dotfiles/backups`. An existing
`~/.ssh/config` gets the gentler treatment: when possible it becomes
`~/.ssh/config.local`, which the tracked config includes. If both files already
exist, SSH config is left alone.

Homebrew packages are deliberately separate from dotfile installation:

```sh
brew bundle --file ~/.files/Brewfile
```

## What is here

- zsh: small PATH setup, native completion, durable history, vi keys, and a
  native Git-aware prompt.
- tmux: `C-a`, vi copy mode, cwd-preserving splits, mouse support, true color,
  and zero plugins.
- Vim + Neovim: one shared, dependency-free editing baseline; launching either
  with no file still gives you the terminal-first workflow this repo was built
  around.
- SSH: a safe `dev` alias plus `~/.ssh/config.local` for machine-specific
  hosts and secrets.
- `devbox`: an Incus-first (LXD-compatible) Ubuntu dev container configured by
  cloud-init before first boot.
- `Brewfile`: the useful command-line layer, without taps, casks, or novelty
  packages.

## Devbox

After `./install`, `~/.local/bin` is on PATH:

```sh
devbox
ssh dev
```

`devbox` prefers Incus and falls back to LXD's `lxc` client. It initializes the
instance, injects `cloud-init/dev.yml` before first boot, starts it, and waits
for cloud-init to finish. Override the defaults without editing the script:

```sh
DEVBOX_NAME=scratch DEVBOX_IMAGE=images:ubuntu/24.04/cloud devbox
```

The provisioned machine clones this repository and runs the same installer, so
the host and dev container do not slowly become two unrelated environments.

## Ground rules

Keep this repository boring in the best sense: readable, inspectable, quick to
load, and safe to run twice. Machine-specific configuration belongs in local
includes; credentials and private keys never belong here.
