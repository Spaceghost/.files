# zshenv - Always sourced.

(( $+commands[brew] )) && export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$(brew --prefix openssl@3)"

# Edit inside the running Neovim (see ~/.config/nvim/init.lua, ~/.bin/nvim-remote).
[[ -d $HOME/.local/bin && ":$PATH:" != *":$HOME/.local/bin:"* ]] && export PATH="$HOME/.local/bin:$PATH"
[[ -d $HOME/.local/nvim/bin && ":$PATH:" != *":$HOME/.local/nvim/bin:"* ]] && export PATH="$HOME/.local/nvim/bin:$PATH"
export PATH="$HOME/.bin:$PATH"
[[ -z ${TMPDIR:-} && -d $HOME/.cache/spaceghost/tmp ]] && export TMPDIR="$HOME/.cache/spaceghost/tmp"
export EDITOR="$HOME/.bin/nvim-remote"
export VISUAL="$EDITOR"
export ENV="$HOME/.ashrc"
[[ -r $HOME/.files/.config/spaceghost/theme.sh ]] && source "$HOME/.files/.config/spaceghost/theme.sh"
