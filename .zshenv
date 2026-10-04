# zshenv - Always sourced.

export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$(brew --prefix openssl@3)"

# Edit inside the running Neovim (see ~/.config/nvim/init.lua, ~/.bin/nvim-remote).
case ":$PATH:" in *":$HOME/.bin:"*) ;; *) export PATH="$HOME/.bin:$PATH" ;; esac
export EDITOR="$HOME/.bin/nvim-remote"
export VISUAL="$EDITOR"
