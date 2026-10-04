# S P A C E G H O S T  /  Z S H
# Behold, $SHELL mode: an interactive terminal lands in Neovim's :terminal.
# zsh stays the login shell; Neovim is the multiplexer (~/.config/nvim/init.lua).
# Skipped inside Neovim, inside tmux (tmux is already the multiplexer there), or
# with SPACEGHOST_PLAIN_SHELL=1 for one plain shell.
if [[ -o interactive && -t 0 && -t 1 && -z $NVIM && -z $TMUX && -z $SPACEGHOST_PLAIN_SHELL ]] \
    && (( $+commands[nvim] )); then
    exec nvim
fi

# ── History / completion ───────────────────────────────────────────────────────
HISTFILE=${XDG_STATE_HOME:-$HOME/.local/state}/zsh/history
HISTSIZE=100000
SAVEHIST=100000
[[ -d ${HISTFILE:h} ]] || mkdir -p "${HISTFILE:h}"
setopt share_history hist_ignore_all_dups hist_ignore_space hist_reduce_blanks
setopt auto_cd auto_pushd pushd_ignore_dups interactive_comments no_beep
autoload -Uz compinit && compinit -i -d "${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}' 'r:|[._-]=* r:|=*'
bindkey -e
bindkey '^[[A' history-beginning-search-backward
bindkey '^[[B' history-beginning-search-forward

# ── Neovim shell integration ───────────────────────────────────────────────────
# OSC 7 tells the hosting Neovim this pane's cwd (new splits open there, the HUD
# shows it); OSC 0 names the tab. Harmless in any other terminal.
spaceghost_precmd() {
    local url="file://${HOST}${PWD}"
    url="${url//\%/%25}"; url="${url// /%20}"
    printf '\e]7;%s\a' "$url"
    printf '\e]0;%s\a' "${PWD/#$HOME/~}"
}
spaceghost_preexec() {
    printf '\e]0;%s\a' "${1%% *}"
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd spaceghost_precmd
add-zsh-hook preexec spaceghost_preexec

# ── Prompt: violet path, mint branch, amber on failure ─────────────────────────
autoload -Uz vcs_info
zstyle ':vcs_info:*' enable git
zstyle ':vcs_info:git:*' formats ' %F{#79efc2}%b%f'
zstyle ':vcs_info:git:*' actionformats ' %F{#f3c969}%b|%a%f'
spaceghost_vcs() { vcs_info }
add-zsh-hook precmd spaceghost_vcs
setopt prompt_subst
PROMPT='%F{#b4a1ff}%~%f${vcs_info_msg_0_} %(?.%F{#79efc2}.%F{#ff7597})❯%f '
RPROMPT='%(1j.%F{#f3c969}%j job%(2j.s.)%f.)'

# ── Aliases for the cockpit ────────────────────────────────────────────────────
alias e='nvim-remote'
alias ls='ls --color=auto'
alias ll='ls -lah'
alias g='git'
