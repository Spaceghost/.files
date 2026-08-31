#!/usr/bin/env bash
set -euo pipefail

version=0.5.3
expected_commit=660c119
container=swayfx-build
source_dir=${SWAYFX_SOURCE_DIR:-$HOME/swayfx}
install_dir="$HOME/.local/opt/swayfx-$version"
scenefx_build_url=https://download.copr.fedorainfracloud.org/results/swayfx/swayfx/fedora-44-x86_64/10699112-scenefx-0.4.1

if [[ ! -d "$source_dir/.git" ]]; then
  git clone --branch "$version" --depth 1 https://github.com/WillPower3309/swayfx.git "$source_dir"
fi

actual_commit=$(git -C "$source_dir" rev-parse --short=7 HEAD)
if [[ "$actual_commit" != "$expected_commit" ]]; then
  printf 'Expected SwayFX %s at %s; found %s in %s.\n' "$version" "$expected_commit" "$actual_commit" "$source_dir" >&2
  exit 1
fi

if ! toolbox list --containers 2>/dev/null | grep -qw "$container"; then
  toolbox create --container "$container" --release 44
fi

toolbox run --container "$container" sudo dnf -y copr enable swayfx/swayfx
toolbox run --container "$container" sudo dnf -y install \
  gcc meson ninja-build scdoc wayland-devel wayland-protocols-devel \
  wlroots0.19-devel json-c-devel libevdev-devel libinput-devel \
  libxkbcommon-devel pango-devel cairo-devel pixman-devel libdrm-devel \
  systemd-devel libxcb-devel xcb-util-wm-devel gdk-pixbuf2-devel
toolbox run --container "$container" sudo dnf -y install \
  "$scenefx_build_url/scenefx-0.4.1-0.4.1-1.fc44.x86_64.rpm" \
  "$scenefx_build_url/scenefx-0.4.1-devel-0.4.1-1.fc44.x86_64.rpm"

meson_setup=(meson setup "$source_dir/build" "$source_dir"
  --prefix="$install_dir" --libdir=lib64 -Dwerror=false -Dswaybar=false -Dswaynag=false -Ddefault-wallpaper=false)
if [[ -d "$source_dir/build" ]]; then
  meson_setup+=(--wipe)
fi
toolbox run --container "$container" "${meson_setup[@]}"
toolbox run --container "$container" meson compile -C "$source_dir/build"
toolbox run --container "$container" meson install -C "$source_dir/build"

mkdir -p "$install_dir/lib64"
toolbox run --container "$container" cp -L /usr/lib64/libscenefx-0.4.so "$install_dir/lib64/libscenefx-0.4.so"
ln -sfn "$install_dir" "$HOME/.local/opt/swayfx"

printf 'Installed SwayFX %s at %s\n' "$version" "$install_dir"
