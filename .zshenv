# Sourced by every zsh. Keep this file fast and side-effect free.
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
