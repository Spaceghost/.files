# .files

A small, fast Unix environment: zsh, tmux, Vim/Neovim, a focused Homebrew
toolset, and a disposable LXD development box.

The rule here is simple: configuration should make the machine quieter and
more useful. Shell startup stays dependency-free, editor defaults work without
a plugin manager, and machine-specific state and secrets stay out of Git.

## Daily use

This repository is designed to use `$HOME` as its work tree with Git metadata
under `~/.config/repo`. The `dotfiles` zsh function keeps normal Git repos and
home-directory Git operations separate:

```sh
dotfiles status
dotfiles diff
dotfiles add ~/.zshrc ~/.tmux.conf
dotfiles commit
dotfiles push
```

Untracked files are hidden by the repository config so `dotfiles status` is
about intentional dotfile changes, not every file in `$HOME`.

## Tooling

`Brewfile` is deliberately short. On macOS or Linux with Homebrew:

```sh
brew bundle --file="$HOME/Brewfile"
```

The shell and editor configs do not depend on Homebrew, so they remain usable
on small Linux systems where packages come from the native package manager.

## Development box

`~/.bin/setup [name]` launches an Ubuntu 24.04 LXD container (named `dev` by
default), waits for cloud-init, and leaves it reachable as `ssh dev` through
mDNS. The cloud-init profile installs the same focused command-line toolset and
imports the Spaceghost GitHub SSH keys.

Set `LXD_IMAGE` or `DOTFILES_DEV_CONFIG_URL` to override the image or cloud-init
profile without editing the script.

## What belongs here

- portable defaults that are useful on more than one machine
- tiny helpers that replace repeated manual work
- development-machine manifests that can be rebuilt from scratch

No credentials, generated caches, plugin lock-in, or ornamental framework
layers. Pull requests run syntax checks against the shell, tmux, editor, and
cloud-init configuration.
