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
Fzf's `Ctrl-T` and `Alt-C` pickers use a colored file/directory preview; press
`Ctrl-/` to move or hide the preview. The shared `spaceghost-preview` command
uses bat and eza when installed. Nushell also loads fzf's key bindings from its
generated autoload script (with a compatibility rewrite for older Nu releases).
Nushell's generated Starship, zoxide, and Atuin integration files live under
`~/.config/nushell/generated/`; `spaceghost-install` refreshes them. The
source-controlled Atuin config is linked to both `~/.atuin/config.toml` and
`~/.config/atuin/config.toml`; an existing XDG config is backed up by the installer.
When `/srv/ai/tmp` exists, shells use that ZFS-backed directory for temporary
files. Else they use `~/.cache/spaceghost/tmp` when available.

On this workstation, install the optional packages with `brew bundle --file
~/.files/Brewfile`. On Alpine, install `fish nushell atuin starship zoxide eza
bat fzf zsh-autosuggestions zsh-syntax-highlighting` with `apk`, then run
`~/.bin/spaceghost-install`. Use `SPACEGHOST_PLAIN_SHELL=1` when you want a
plain shell instead of automatically attaching to the Neovim session.
Run `~/.files/tests/shell-configs.sh` to check shell syntax, aliases, the
Starship prompt, and the `ocodex` argument forwarding.

The modular approach follows examples from
[John Stegeman's fish/Tide/Atuin dotfiles](https://github.com/johnstegeman/dotfiles)
and [chiptoma's zsh modules](https://github.com/chiptoma/dotfiles-zsh), plus
[kursataknc's Ghostty/Nushell setup](https://github.com/kursataknc/dotfiles)
and [jsoyer's cross-tool theme index](https://github.com/jsoyer/dotfiles/blob/main/dot_config/CONFIGURATION_INDEX.md).
Integration syntax follows [Atuin](https://docs.atuin.sh/main/guide/installation/),
[Starship](https://starship.rs/config/), and
[Nushell](https://www.nushell.sh/book/configuration.html) documentation;
the preview widgets follow [fzf's shell integration](https://github.com/junegunn/fzf#key-bindings-for-command-line).
