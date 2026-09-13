# Spaceghost interactive shell — Catppuccin Mocha.  Kept self-contained: no framework or network installer.
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
# Catppuccin Mocha file colors: directories, links, executables, archives, and images.
export LS_COLORS='di=38;2;249;226;175:ln=38;2;148;226;213:ex=38;2;166;227;161:or=38;2;243;139;168:*.tar=38;2;250;179;135:*.gz=38;2;250;179;135:*.zip=38;2;250;179;135:*.png=38;2;203;166;247:*.jpg=38;2;203;166;247:*.webp=38;2;203;166;247'
export EZA_COLORS="${LS_COLORS}:uu=38;2;137;180;250:gu=38;2;108;112;134:da=38;2;166;173;200:sn=38;2;205;214;244"
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

# Space Ghost splash: once per terminal, never inside tmux, only on a real TTY.
# oldbook-splash picks the image protocol; nested shells inherit the guard.
if [[ -z $OLDBOOK_SPLASH && -z $TMUX && -t 1 && -x $HOME/.local/bin/oldbook-splash ]]; then
    export OLDBOOK_SPLASH=1
    "$HOME/.local/bin/oldbook-splash"
fi
