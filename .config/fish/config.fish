# Spaceghost shell: same commands and colors as the Neovim cockpit.
fish_add_path --path $HOME/.bin $HOME/.local/bin $HOME/.local/nvim/bin
if not set -q TMPDIR; and test -d $HOME/.cache/spaceghost/tmp
    set -gx TMPDIR $HOME/.cache/spaceghost/tmp
end
set -gx EDITOR $HOME/.bin/nvim-remote
set -gx VISUAL $EDITOR
set -gx ENV $HOME/.ashrc
set -gx FZF_DEFAULT_OPTS '--height=45% --layout=reverse --border=rounded --prompt=❯ --pointer=▶ --marker=✓ --color=fg:#e8edf7,bg:#0b0d16,hl:#b4a1ff,fg+:#e8edf7,bg+:#2b3148,hl+:#79efc2,info:#8992ad,prompt:#79efc2,pointer:#b4a1ff,marker:#f3c969,border:#5a6280'

if status is-interactive
if test -t 0; and test -t 1; and not set -q NVIM; and not set -q TMUX; and not set -q SPACEGHOST_PLAIN_SHELL
    if command -q nvim
        exec $HOME/.bin/nvim-attach
    end
end

set -g fish_greeting
set -g fish_color_command 79efc2
set -g fish_color_keyword b4a1ff
set -g fish_color_param e8edf7
set -g fish_color_quote f3c969
set -g fish_color_error ff7597
set -g fish_color_autosuggestion 5a6280
set -g fish_color_cwd b4a1ff
set -g fish_color_operator 7fe3f0
set -g fish_color_selection --background=2b3148
set -g fish_pager_color_selected_background --background=2b3148

alias e nvim-remote
alias v nvim-remote
alias a nvim-attach
alias g git
alias gs 'git status --short --branch'
alias gd 'git diff'
alias m mosh
alias c clear
if command -q eza
    alias ls 'eza --icons=auto --group-directories-first'
    alias l 'eza --icons=auto --group-directories-first'
    alias la 'eza -a --icons=auto --group-directories-first'
    alias ll 'eza -lah --icons=auto --group-directories-first --git'
else
    alias l ls
    alias la 'ls -a'
    alias ll 'ls -lah'
end
if command -q bat
    alias b 'bat --paging=never'
end
if command -q atuin
    alias h 'atuin search'
end

if command -q zoxide
    zoxide init fish | source
end
if command -q fzf
    fzf --fish | source
end
if command -q starship
    starship init fish | source
else
    function fish_prompt
        set_color b4a1ff
        printf '✦ %s ' (prompt_pwd)
        set_color 79efc2
        printf '❯ '
        set_color normal
    end
end
if command -q atuin
    atuin init fish | source
end
end
