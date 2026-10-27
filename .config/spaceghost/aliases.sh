# Shared interactive aliases for POSIX sh, ash, bash, and zsh.
if [ -z "${TMPDIR:-}" ]; then
    for spaceghost_tmp in /srv/ai/tmp "$HOME/.cache/spaceghost/tmp"; do
        if [ -d "$spaceghost_tmp" ] && [ -w "$spaceghost_tmp" ]; then
            TMPDIR="$spaceghost_tmp"; export TMPDIR
            break
        fi
    done
    unset spaceghost_tmp
fi
if [ "${TMPDIR:-}" = /srv/ai/tmp ]; then
    AI_WORKSPACE_ROOT=/srv/ai; TMP="$TMPDIR"; TEMP="$TMPDIR"
    export AI_WORKSPACE_ROOT TMP TEMP
fi
alias e='nvim-remote'
alias v='nvim-remote'
alias a='nvim-attach'
alias g='git'
alias gs='git status --short --branch'
alias gd='git diff'
alias m='mosh'
alias c='clear'

if command -v eza >/dev/null 2>&1; then
    alias ls='eza --icons=auto --group-directories-first'
    alias l='eza --icons=auto --group-directories-first'
    alias la='eza -a --icons=auto --group-directories-first'
    alias ll='eza -lah --icons=auto --group-directories-first --git'
else
    alias l='ls'
    alias la='ls -a'
    alias ll='ls -lah'
fi
command -v bat >/dev/null 2>&1 && alias b='bat --paging=never'
command -v atuin >/dev/null 2>&1 && alias h='atuin search'
