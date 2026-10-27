# Shells

`ocodex` and `oclaude` are executables in `~/.bin`, so they work from ash,
Bash, fish, zsh, Nushell, and scripts. They preserve the flags from the old
Bash aliases. The CLI shortcuts `e`, `v`, `a`, `g`, `gs`, `gd`, `m`, `c`, `l`,
`la`, and `ll` are shared across interactive shells. Nushell keeps its own
structured `ls`; its `l`/`la`/`ll` use eza when present.

| Shell | Config | Interactive features |
| --- | --- | --- |
| zsh | `.zshrc`, `.zshenv` | Starship prompt, Atuin history, zoxide, fzf, suggestions, syntax colors, OSC 7/0/133 |
| Bash | `.bash_spaceghost`, sourced by `.bashrc`/`.profile` | Starship, Atuin, zoxide, fzf |
| ash | `.ashrc`, loaded through `ENV` | Fast Unicode prompt and shared aliases |
| fish | `.config/fish/config.fish` | Starship, Atuin, zoxide, fzf, themed syntax colors |
| Nushell | `.config/nushell/config.nu` | Starship, Atuin, rounded tables, eza list commands |

Starship and Atuin use the Spaceghost violet/mint/amber palette. Optional tools
are detected at startup, so the shells still open if a package is missing.
Nushell's generated Starship, zoxide, and Atuin integration files live under
`~/.config/nushell/generated/`; `spaceghost-install` refreshes them. The
source-controlled Atuin config is linked to `~/.atuin/config.toml`; an existing
custom config is preserved by the installer.

On this workstation, install the optional packages with `brew bundle --file
~/.files/Brewfile`. On Alpine, install `fish nushell atuin starship zoxide eza
bat fzf zsh-autosuggestions zsh-syntax-highlighting` with `apk`, then run
`~/.bin/spaceghost-install`. Use `SPACEGHOST_PLAIN_SHELL=1` when you want a
plain shell instead of automatically attaching to the Neovim session.
Run `~/.files/tests/shell-configs.sh` to check shell syntax, aliases, the
Starship prompt, and the `ocodex` argument forwarding.

The modular approach follows examples from
[John Stegeman's fish/Tide/Atuin dotfiles](https://github.com/johnstegeman/dotfiles)
and [chiptoma's zsh modules](https://github.com/chiptoma/dotfiles-zsh).
Integration syntax follows [Atuin](https://docs.atuin.sh/main/guide/installation/),
[Starship](https://starship.rs/config/), and
[Nushell](https://www.nushell.sh/book/configuration.html) documentation.
