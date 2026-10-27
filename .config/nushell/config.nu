# Spaceghost Nushell: structured output with the same cockpit palette.
let bin = $"($env.HOME)/.bin"
let local_bin = $"($env.HOME)/.local/bin"
let nvim_bin = $"($env.HOME)/.local/nvim/bin"
if ($local_bin | path exists) and $local_bin not-in $env.PATH {
    $env.PATH = ($env.PATH | prepend $local_bin)
}
if ($nvim_bin | path exists) and $nvim_bin not-in $env.PATH {
    $env.PATH = ($env.PATH | prepend $nvim_bin)
}
$env.PATH = ($env.PATH | where $it != $bin | prepend $bin)
$env.EDITOR = $"($env.HOME)/.bin/nvim-remote"
$env.VISUAL = $env.EDITOR
$env.ENV = $"($env.HOME)/.ashrc"
let private_tmp = $"($env.HOME)/.cache/spaceghost/tmp"
if 'TMPDIR' not-in $env {
    if ('/srv/ai/tmp' | path exists) { $env.TMPDIR = '/srv/ai/tmp' }
    else if ($private_tmp | path exists) { $env.TMPDIR = $private_tmp }
}
if ('TMPDIR' in $env) and ($env.TMPDIR == '/srv/ai/tmp') {
    $env.AI_WORKSPACE_ROOT = '/srv/ai'
    $env.TMP = $env.TMPDIR
    $env.TEMP = $env.TMPDIR
}
$env.FZF_DEFAULT_OPTS = '--height=45% --layout=reverse --border=rounded --prompt=❯ --pointer=▶ --marker=✓ --color=fg:#e8edf7,bg:#0b0d16,hl:#b4a1ff,fg+:#e8edf7,bg+:#2b3148,hl+:#79efc2,info:#8992ad,prompt:#79efc2,pointer:#b4a1ff,marker:#f3c969,border:#5a6280'
$env.FZF_CTRL_T_OPTS = "--walker-skip .git,node_modules,target --preview 'spaceghost-preview {}' --preview-window 'right,55%,border-left' --bind 'ctrl-/:change-preview-window(down|hidden|right)'"
$env.FZF_ALT_C_OPTS = $env.FZF_CTRL_T_OPTS

$env.config.show_banner = false
$env.config.table.mode = 'rounded'
$env.config.history.max_size = 100000

alias e = ^nvim-remote
alias v = ^nvim-remote
alias a = ^nvim-attach
alias g = ^git
alias gs = ^git status --short --branch
alias gd = ^git diff
alias m = ^mosh
alias c = clear
alias h = ^atuin search

def --wrapped l [...rest] {
    let paths = if ($rest | is-empty) { [.] } else { $rest }
    if (which eza | is-empty) { ls ...$paths } else { ^eza --icons=auto --group-directories-first ...$paths }
}
def --wrapped la [...rest] {
    let paths = if ($rest | is-empty) { [.] } else { $rest }
    if (which eza | is-empty) { ls -a ...$paths } else { ^eza -a --icons=auto --group-directories-first ...$paths }
}
def --wrapped ll [...rest] {
    let paths = if ($rest | is-empty) { [.] } else { $rest }
    if (which eza | is-empty) { ls -la ...$paths } else { ^eza -lah --icons=auto --group-directories-first --git ...$paths }
}

$env.PROMPT_COMMAND = {||
    $"(ansi {fg: '#b4a1ff'})✦ (pwd | path basename)(ansi reset) "
}
$env.PROMPT_INDICATOR = {|| $"(ansi {fg: '#79efc2'})❯ (ansi reset)" }

# Nushell sources generated integrations from static paths at parse time.
const starship_init = if ('~/.config/nushell/generated/starship.nu' | path exists) {
    '~/.config/nushell/generated/starship.nu'
} else { null }
source $starship_init
const zoxide_init = if ('~/.config/nushell/generated/zoxide.nu' | path exists) {
    '~/.config/nushell/generated/zoxide.nu'
} else { null }
source $zoxide_init
const atuin_init = if ('~/.config/nushell/generated/atuin.nu' | path exists) {
    '~/.config/nushell/generated/atuin.nu'
} else { null }
source $atuin_init

if $nu.is-interactive and (is-terminal --stdin) and (is-terminal --stdout) and ('NVIM' not-in $env) and ('TMUX' not-in $env) and ('SPACEGHOST_PLAIN_SHELL' not-in $env) and (which nvim | is-not-empty) {
    exec $"($env.HOME)/.bin/nvim-attach"
}
