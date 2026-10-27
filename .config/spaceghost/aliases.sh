# Shared interactive aliases for POSIX sh, ash, bash, and zsh.
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
