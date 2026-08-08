# zshenv - Always sourced. Keep it fast and safe for non-interactive shells.

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"

typeset -gU path PATH
path=(
  "$HOME/.local/bin"
  "$HOME/.bin"
  /opt/homebrew/bin
  /home/linuxbrew/.linuxbrew/bin
  $path
)
export PATH

if (( $+commands[brew] )); then
  export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$(brew --prefix openssl@3)"
fi
