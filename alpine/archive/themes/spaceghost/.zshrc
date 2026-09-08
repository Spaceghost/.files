# Spaceghost interactive shell.  Kept self-contained: no framework or network installer.
[[ -o interactive ]] || return

export EDITOR=nvim
export VISUAL=nvim
export PAGER='less -FRX'
export LESS='-R'
export QT_QPA_PLATFORMTHEME=qt6ct
export GTK_THEME=adw-gtk3-dark
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

HISTFILE="${XDG_STATE_HOME:-$HOME/.local/state}/zsh/history"
HISTSIZE=50000
SAVEHIST=50000
mkdir -p "${HISTFILE:h}"
setopt append_history inc_append_history share_history hist_ignore_dups hist_reduce_blanks
setopt auto_cd auto_pushd pushd_ignore_dups interactive_comments
bindkey -e

mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}/zsh"

autoload -Uz compinit
compinit -d "${XDG_CACHE_HOME:-$HOME/.cache}/zsh/zcompdump"
zstyle ':completion:*' menu select
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"

alias ls='eza --icons --group-directories-first'
alias ll='eza -lah --icons --group-directories-first'
alias fs='fossil status'
alias fdiff='fossil diff'
alias rice='cd ~/.files/alpine/desktop'
alias scene='oldbook-wallpaper next'
alias la='eza -a --icons --group-directories-first'
alias v='nvim'
alias c='clear'
command -v zoxide >/dev/null && eval "$(zoxide init zsh)"
command -v starship >/dev/null && eval "$(starship init zsh)"
