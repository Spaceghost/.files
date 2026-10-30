# S P A C E G H O S T  /  Z S H
# Behold, $SHELL mode: an interactive terminal lands in Neovim's :terminal.
# zsh stays the login shell; Neovim is the multiplexer (~/.config/nvim/init.lua).
# Skipped inside Neovim, inside tmux (tmux is already the multiplexer there), or
# with SPACEGHOST_PLAIN_SHELL=1 for one plain shell.
# Terminals attach to this machine's persistent session (nvim-session); :detach leaves it running.
if [[ -o interactive && -t 0 && -t 1 && -z $NVIM && -z $TMUX && -z $SPACEGHOST_PLAIN_SHELL ]] \
    && (( $+commands[nvim] )); then
    exec "$HOME/.bin/nvim-attach"
fi

# ── History / completion ───────────────────────────────────────────────────────
HISTFILE=${XDG_STATE_HOME:-$HOME/.local/state}/zsh/history
HISTSIZE=100000
SAVEHIST=100000
[[ -d ${HISTFILE:h} ]] || mkdir -p "${HISTFILE:h}"
setopt share_history hist_ignore_all_dups hist_ignore_space hist_reduce_blanks
setopt auto_cd auto_pushd pushd_ignore_dups interactive_comments no_beep
setopt extended_glob auto_list complete_in_word
autoload -Uz compinit && compinit -i -d "${XDG_CACHE_HOME:-$HOME/.cache}/zsh/compdump"
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}' 'r:|[._-]=* r:|=*'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
bindkey -e
bindkey '^[[A' history-beginning-search-backward
bindkey '^[[B' history-beginning-search-forward
bindkey '^[[Z' reverse-menu-complete

# ── Neovim shell integration ───────────────────────────────────────────────────
# OSC 7 tells the hosting Neovim this pane's cwd (new splits open there, the HUD
# shows it); OSC 0 names the tab. OSC 133 marks prompts for scrollback jumps.
spaceghost_precmd() {
    local url="file://${HOST}${PWD}"
    url="${url//\%/%25}"; url="${url// /%20}"
    printf '\e]7;%s\a' "$url"
    printf '\e]0;%s\a' "${PWD/#$HOME/~}"
    [[ -n $NVIM ]] && printf '\e]133;A\e\\'
}
spaceghost_preexec() {
    [[ -n $NVIM ]] && printf '\e]133;B\e\\'
    printf '\e]0;%s\a' "${1%% *}"
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd spaceghost_precmd
add-zsh-hook preexec spaceghost_preexec

# ── Cockpit commands and optional tools ────────────────────────────────────────
for spaceghost_dir in "$HOME/.files" "$HOME/.spaceghost"; do
    [[ -r $spaceghost_dir/.config/spaceghost/aliases.sh ]] || continue
    source "$spaceghost_dir/.config/spaceghost/aliases.sh"
    break
done
unset spaceghost_dir
[[ -z $ENV ]] && export ENV="$HOME/.ashrc"

if (( $+commands[zoxide] )); then eval "$(zoxide init zsh)"; fi
if (( $+commands[fzf] )); then eval "$(fzf --zsh)"; fi

if (( $+commands[starship] )); then
    eval "$(starship init zsh)"
else
    autoload -Uz vcs_info
    zstyle ':vcs_info:*' enable git
    zstyle ':vcs_info:git:*' formats ' %F{#79efc2}%b%f'
    zstyle ':vcs_info:git:*' actionformats ' %F{#f3c969}%b|%a%f'
    spaceghost_vcs() { vcs_info }
    add-zsh-hook precmd spaceghost_vcs
    setopt prompt_subst
    PROMPT='%F{#b4a1ff}%~%f${vcs_info_msg_0_} %(?.%F{#79efc2}.%F{#ff7597})❯%f '
    RPROMPT='%(1j.%F{#f3c969}%j job%(2j.s.)%f.)'
fi

if (( $+commands[atuin] )); then eval "$(atuin init zsh)"; fi
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#5a6280'
for plugin in /home/linuxbrew/.linuxbrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh \
    /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh \
    /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh \
    /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh; do
    [[ -r $plugin ]] && { source "$plugin"; break; }
done
unset plugin

# Syntax highlighting must be sourced after the other ZLE integrations.
for plugin in /home/linuxbrew/.linuxbrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh \
    /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh \
    /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh \
    /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh; do
    [[ -r $plugin ]] && { source "$plugin"; break; }
done
unset plugin
if (( ${+ZSH_HIGHLIGHT_STYLES} )); then
    ZSH_HIGHLIGHT_STYLES[command]='fg=#79efc2'
    ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#ff7597,bold'
    ZSH_HIGHLIGHT_STYLES[path]='fg=#7fb7ff,underline'
fi
