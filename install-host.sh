#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mapfile -t packages < <(sed -E '/^[[:space:]]*(#|$)/d' "$repo_dir/packages/fedora-atomic.txt")

if rpm-ostree status | grep -q '^State: busy'; then
  printf 'rpm-ostree is busy with another transaction; retry after it completes.\n' >&2
  exit 1
fi

sudo rpm-ostree install "${packages[@]}"
sudo install -Dm755 "$repo_dir/.local/bin/swayfx-session" /usr/local/bin/swayfx-session
sudo install -Dm644 "$repo_dir/.local/share/wayland-sessions/swayfx.desktop" /usr/local/share/wayland-sessions/swayfx.desktop

printf 'Host packages and SwayFX session entry installed. Reboot into the staged deployment.\n'
