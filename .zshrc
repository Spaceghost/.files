[[ -o interactive ]] || return

HISTFILE=$XDG_STATE_HOME/zsh/history
HISTSIZE=50000
SAVEHIST=50000

if [[ ! -d ${HISTFILE:h} ]]; then
  mkdir -p -m 700 "${HISTFILE:h}"
fi

setopt EXTENDED_HISTORY
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_REDUCE_BLANKS
setopt SHARE_HISTORY
setopt INTERACTIVE_COMMENTS
setopt PROMPT_SUBST
unsetopt BEEP

autoload -Uz compinit vcs_info
cache_dir=$XDG_CACHE_HOME/zsh
mkdir -p -m 700 "$cache_dir"
if [[ -s $cache_dir/zcompdump ]]; then
  compinit -C -d "$cache_dir/zcompdump"
else
  compinit -d "$cache_dir/zcompdump"
fi
unset cache_dir

zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':vcs_info:git:*' formats ' %F{244}%b%f'

typeset -ga precmd_functions
if (( ! ${precmd_functions[(I)vcs_info]} )); then
  precmd_functions+=(vcs_info)
fi

bindkey -v
KEYTIMEOUT=1

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
  brew_prefix=${commands[brew]:h:h}
  if [[ -d $brew_prefix/opt/openssl@3 ]]; then
    export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$brew_prefix/opt/openssl@3"
  fi
  unset brew_prefix
fi

dotfiles() {
  git -C "${DOTFILES_DIR:-$HOME/.files}" "$@"
}

if [[ -n ${SSH_CONNECTION:-} ]]; then
  PROMPT='%F{245}%n@%m%f %F{39}%~%f${vcs_info_msg_0_} %# '
else
  PROMPT='%F{39}%~%f${vcs_info_msg_0_} %# '
fi
