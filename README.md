# .files

Personal dotfiles and rebuildable development-machine bits.

This is a working environment, not a generic starter kit. Some files encode
specific workflows that are easy to mistake for duplication. The rule for this
repo is therefore: **preserve first, simplify only after the purpose is clear.**

## What's here

- `.zshenv` and `.zshrc` — shell environment and interactive zsh behavior
- `.vimrc` and `.config/nvim/` — the existing Vim and Neovim paths
- `.tmux.conf` — the established tmux key bindings, status setup, and TPM plugins
- `Brewfile` — the Homebrew/Linuxbrew tool manifest
- `.bin/setup` — the LXD development-instance launcher
- `.bin/👻` — the tiny asdf Ruby-plugin helper
- `.config/repo/config` — the dotfiles repository's existing multi-remote Git setup
- `cloud-init/` — distinct provisioning recipes, intentionally kept separate

The cloud-init files are not treated as interchangeable:

- `devbuntu.cloud.config.yml` is the general LXD/cloud-init configuration
- `devbuntu.mdns.config.yml` is the mDNS LXD configuration used by `.bin/setup`
- `devbuntu.mdns.yml` is the raw mDNS cloud-config form
- `docker.yml` is the separate Docker provisioning recipe

## Daily use

The repository uses `$HOME` as its work tree with Git metadata under
`~/.config/repo`. Interactive zsh exposes a `dotfiles` helper so ordinary
repositories remain ordinary:

```sh
dotfiles status
dotfiles diff
dotfiles add ~/.zshrc
dotfiles commit
dotfiles push
```

Untracked files remain hidden by the repository's own config, as before.

## Tooling

On a machine with Homebrew:

```sh
brew bundle --file="$HOME/Brewfile"
```

The manifest keeps the existing toolset and adds only a few obvious companions
for files already in the repo: Neovim, jq, and OpenSSL 3.

## Development box

`~/.bin/setup [name]` keeps the existing `ubuntu:` image and
`spacegho.st` cloud-init source by default. It now fails clearly when `lxc`
is missing or the target already exists and waits for cloud-init to finish.

`LXD_IMAGE` and `DOTFILES_DEV_CONFIG_URL` are optional overrides.

## Change rule

Improve things in place. Do not delete or consolidate an existing file merely
because it looks old, redundant, or unusual. First establish what consumes it
and what behavior would be lost; if that cannot be established, preserve it.
