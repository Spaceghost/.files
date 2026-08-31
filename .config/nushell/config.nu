$env.config = {
  show_banner: false
  edit_mode: vi
  cursor_shape: { vi_insert: line, vi_normal: block }
  table: { mode: rounded, index_mode: auto, show_empty: true, padding: { left: 1, right: 1 } }
  history: { file_format: sqlite, max_size: 100_000, sync_on_enter: true, isolation: false }
  completions: {
    case_sensitive: false
    quick: true
    partial: true
    algorithm: fuzzy
    use_ls_colors: true
    external: { enable: true, max_results: 100, completer: null }
  }
}

$env.EDITOR = "vi"
$env.VISUAL = "vi"
$env.PAGER = "less -FRX"
$env.PATH = ($env.PATH | prepend ($nu.home-path | path join ".local" "bin") | uniq)

alias ll = ls -la
alias la = ls -a
alias gs = git status --short --branch
alias gl = git log --oneline --decorate --graph -20

def --env mkcd [directory: path] {
  mkdir $directory
  cd $directory
}

def desktop-status [] {
  {
    compositor: ($env.XDG_CURRENT_DESKTOP? | default "unknown")
    sway_socket: ($env.SWAYSOCK? | default "not running")
    shell: "nushell"
  }
}

