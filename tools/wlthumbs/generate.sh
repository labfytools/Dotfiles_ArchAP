#!/usr/bin/env bash
# Regenerate the Wayland protocol bindings in proto/ from the XML in protocol/.
#
# The bindings are committed so normal builds need no network or codegen; run
# this only when bumping a protocol. After running, re-apply the manual patch
# noted at the bottom.
set -euo pipefail
cd "$(dirname "$0")"

SCANNER="github.com/rajveermalviya/go-wayland/cmd/go-wayland-scanner@latest"

gen() { # <xml> <out> <pkg-suffix-stripped-name>
    go run "$SCANNER" -pkg proto -suffix v1 -o "proto/$2" -i "protocol/$1"
}

gen ext-foreign-toplevel-list-v1.xml ext_foreign_toplevel_list.go
gen ext-image-capture-source-v1.xml ext_image_capture_source.go
gen ext-image-copy-capture-v1.xml   ext_image_copy_capture.go

cat <<'NOTE'

Bindings regenerated.

MANUAL PATCH REQUIRED (see proto/register.go for the why):
  In proto/ext_foreign_toplevel_list.go, the generated Dispatch for the
  `toplevel` event does:

      e.Toplevel = i.Context().GetProxy(client.Uint32(data[l : l+4])).(*ExtForeignToplevelHandle)

  That panics because the toplevel arg is a *server*-allocated new_id that was
  never registered client-side. Replace it with:

      toplevelID := client.Uint32(data[l : l+4])
      handle := &ExtForeignToplevelHandle{}
      registerServerObject(i.Context(), toplevelID, handle)
      e.Toplevel = handle

Then: gofmt -w proto/*.go && go build ./...
NOTE
