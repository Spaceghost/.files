# Interactive shell: useful defaults, no framework and no network work.

HISTFILE="$XDG_STATE_HOME/zsh/history"
HISTSIZE=50000
SAVEHIST=50000
if [[ ! -d ${HISTFILE:h} ]]; then
  mkdir -p -m 700 "${HISTFILE:h}"
fi

setopt append_history
setopt extended_history
setopt hist_ignore_all_dups
setopt hist_reduce_blanks
setopt interactive_comments
setopt share_history

bindkey -v
KEYTIMEOUT=1

autoload -Uz compinit
_zcompdump="$XDG_CACHE_HOME/zsh/zcompdump"
if [[ ! -d ${_zcompdump:h} ]]; then
  mkdir -p -m 700 "${_zcompdump:h}"
fi
if [[ -s $_zcompdump ]]; then
  compinit -C -d "$_zcompdump"
else
  compinit -d "$_zcompdump"
fi
unset _zcompdump

if (( $+commands[nvim] )); then
  export EDITOR=nvim
  export VISUAL=nvim
elif (( $+commands[vim] )); then
  export EDITOR=vim
  export VISUAL=vim
fi
export PAGER=less
export LESS='-FRX'

if (( $+commands[brew] )); then
  _brew_prefix=${commands[brew]:h:h}
  if [[ -d $_brew_prefix/opt/openssl@3 ]]; then
    export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$_brew_prefix/opt/openssl@3"
  fi
  unset _brew_prefix
fi

dotfiles() {
  git --git-dir="${DOTFILES_GIT_DIR:-$HOME/.config/repo}" --work-tree="$HOME" "$@"
}

PROMPT='%F{cyan}%n@%m%f %F{blue}%~%f %# '
