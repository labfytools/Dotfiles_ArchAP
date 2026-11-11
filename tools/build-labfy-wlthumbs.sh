#!/usr/bin/env bash
# Build the audited, MIT-licensed, ID-filtered Wayland window snapshot helper.
# User scope only. No sudo, no package installation and no session restart.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
src="$root/wlthumbs"
dest="$HOME/.local/libexec"
mkdir -p -- "$dest"
tmp="$(mktemp -- "$dest/.labfy-wlthumbs.XXXXXXXX")"
trap 'rm -f -- "$tmp"' EXIT

(
    cd -- "$src"
    CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o "$tmp" .
)
chmod 755 "$tmp"
mv -f -- "$tmp" "$dest/labfy-wlthumbs"
printf 'Binary installed: %s/labfy-wlthumbs\n' "$dest"
sha256sum "$dest/labfy-wlthumbs"
