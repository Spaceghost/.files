# Shared fzf palette for POSIX shells and zsh.
FZF_DEFAULT_OPTS='--height=45% --layout=reverse --border=rounded --prompt=❯ --pointer=▶ --marker=✓ --color=fg:#e8edf7,bg:#0b0d16,hl:#b4a1ff,fg+:#e8edf7,bg+:#2b3148,hl+:#79efc2,info:#8992ad,prompt:#79efc2,pointer:#b4a1ff,marker:#f3c969,border:#5a6280'
export FZF_DEFAULT_OPTS
# fzf parses the quotes in these option strings itself.
# shellcheck disable=SC2089
FZF_CTRL_T_OPTS="--walker-skip .git,node_modules,target --preview 'spaceghost-preview {}' --preview-window 'right,55%,border-left' --bind 'ctrl-/:change-preview-window(down|hidden|right)'"
FZF_ALT_C_OPTS="$FZF_CTRL_T_OPTS"
# shellcheck disable=SC2090
export FZF_CTRL_T_OPTS FZF_ALT_C_OPTS
