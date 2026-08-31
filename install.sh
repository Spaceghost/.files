#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
backup_root="$HOME/.local/state/sway-desktop-backups/$(date +%Y%m%d-%H%M%S)"

link_one() {
  local relative=$1 source target
  source="$repo_dir/$relative"
  target="$HOME/$relative"
  mkdir -p -- "$(dirname -- "$target")"

  if [[ -L "$target" && $(readlink -f -- "$target") == $(readlink -f -- "$source") ]]; then
    return
  fi
  if [[ -e "$target" || -L "$target" ]]; then
    mkdir -p -- "$backup_root/$(dirname -- "$relative")"
    mv -- "$target" "$backup_root/$relative"
  fi
  ln -s -- "$source" "$target"
}

while IFS= read -r -d '' source; do
  relative=${source#"$repo_dir/"}
  case "$relative" in
    .git/*|.gitignore|README.md|install.sh|install-host.sh|build-swayfx.sh|packages/*|assets/*) continue ;;
  esac
  link_one "$relative"
done < <(find "$repo_dir" -type f -print0)

printf 'User configuration linked from %s\n' "$repo_dir"
if [[ -d "$backup_root" ]]; then
  printf 'Previous files backed up under %s\n' "$backup_root"
fi
printf 'Reload Sway with Mod+Shift+c. A full logout is required for session-level changes.\n'

