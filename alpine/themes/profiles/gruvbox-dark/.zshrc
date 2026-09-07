# Spaceghost interactive shell — Gruvbox Dark.  Kept self-contained: no framework or network installer.
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
# Gruvbox file colors: directories, links, executables, archives, and images.
export LS_COLORS='di=38;2;250;189;47:ln=38;2;142;192;124:ex=38;2;184;187;38:or=38;2;251;73;52:*.tar=38;2;254;128;25:*.gz=38;2;254;128;25:*.zip=38;2;254;128;25:*.png=38;2;211;134;155:*.jpg=38;2;211;134;155:*.webp=38;2;211;134;155'
export EZA_COLORS="${LS_COLORS}:uu=38;2;131;165;152:gu=38;2;146;131;116:da=38;2;168;153;132:sn=38;2;235;219;178"
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
