#!/bin/sh
# Compile the layer-shell animator used by measure.py and live-probe.py.
# It is one C file, it links only libwayland-client, and it installs nothing.
# The layer-shell protocol description is not on this machine outside a source
# tree, so point --protocol at the copy inside the SwayFX tarball:
#     protocols/wlr-layer-shell-unstable-v1.xml
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${OUT:-/tmp/layeranim}
protocol=${1:-}
if [ -z "$protocol" ] || [ ! -f "$protocol" ]; then
    echo "usage: $0 /path/to/wlr-layer-shell-unstable-v1.xml" >&2
    echo "  (it ships in the SwayFX source tarball under protocols/)" >&2
    exit 2
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
wayland-scanner client-header "$protocol" "$work/wlr-layer-shell-unstable-v1-client-protocol.h"
wayland-scanner private-code  "$protocol" "$work/wlr-layer-shell-unstable-v1-protocol.c"
xdg=$(pkg-config --variable=pkgdatadir wayland-protocols)
wayland-scanner client-header "$xdg/stable/xdg-shell/xdg-shell.xml" "$work/xdg-shell-client-protocol.h"
wayland-scanner private-code  "$xdg/stable/xdg-shell/xdg-shell.xml" "$work/xdg-shell-protocol.c"
cc -O2 -std=c11 -I"$work" "$here/layeranim.c" \
   "$work/wlr-layer-shell-unstable-v1-protocol.c" "$work/xdg-shell-protocol.c" \
   -o "$out" $(pkg-config --cflags --libs wayland-client) -lrt
echo "$out"
