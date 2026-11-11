# wlthumbs

A tiny Wayland client that captures thumbnails of every open window (and,
optionally, every monitor) over a **single** Wayland connection, using the
wlroots capture protocols:

- `ext-foreign-toplevel-list-v1` — enumerate windows
- `ext-image-capture-source-v1` — a capture source from a toplevel handle or output
- `ext-image-copy-capture-v1` — copy a frame into a `wl_shm` buffer

It scales each frame in-process and writes a small PNG, printing one
tab-separated row per source:

```
TYPE <TAB> ID <TAB> THUMBPATH <TAB> APP <TAB> TITLE
```

- `TYPE` — `window` or `output`
- `ID` — the window's `foreign_toplevel_identifier` (matches sway's
  `foreign_toplevel_identifier`) or the output name (e.g. `DP-1`)
- `THUMBPATH` — path to the PNG, or empty if that source failed to capture
- `APP` — `app_id` (window) or `make model` (output)
- `TITLE` — window title, or output name

It does one thing: dump window/monitor thumbnails for a shell front-end (e.g. a
rofi grid) to consume. It does **not** draw any UI.

## Usage

```
wlthumbs [-size N] [-dir DIR] [-windows] [-outputs]
```

- `-size N`     max thumbnail dimension in px (default 256)
- `-dir DIR`    output directory (default: a fresh temp dir under `$XDG_RUNTIME_DIR`)
- `-windows`    capture windows (default true)
- `-outputs`    also capture monitors (default false)

Each thumbnail is named `<ID>.png` (the ID column), so a caller that already
knows the id can find the file directly — `"$dir/$id.png"` — without parsing
stdout; a missing file means that source failed to capture.

The caller owns `-dir`'s lifetime — wlthumbs never deletes thumbnails (a front-end
typically reads them after wlthumbs exits). With no `-dir`, PNGs land in a temp dir
under `$XDG_RUNTIME_DIR` that you should clean up yourself.

Set `WLTHUMBS_TIME=1` to print phase timings to stderr.

Example — thumbnail every window, then feed a rofi grid:

```sh
wlthumbs -size 220 | while IFS=$'\t' read -r type id thumb app title; do
    printf '%s\x00icon\x1f%s\n' "$title" "$thumb"
done | rofi -dmenu -show-icons
```

## Building

```
go build -o wlthumbs .
```

Requires a wlroots-based compositor (sway, etc.) advertising the three `ext-*`
protocols above. Pure Go — no cgo.

## Notes

- Captures run sequentially on the one connection (wlroots does not parallelize
  them); each frame is scaled/encoded on a worker goroutine while the next window
  is captured, so encode cost hides under capture time.
- The protocol bindings in `proto/` are generated from the XML in `protocol/`
  and committed. See `generate.sh` to regenerate (and the manual patch it
  documents).
- Two go-wayland quirks are worked around in the code: `Registry.Bind` writing a
  padded string length (rejected by newer libwayland — see `bind` in
  `wayland.go`), and no support for server-allocated objects (see
  `proto/register.go`).

## Source layout

- `main.go` — CLI flags, orchestration, phase timing (`WLTHUMBS_TIME`)
- `wayland.go` — the Wayland client: connect/bind globals, enumerate toplevels
  and outputs, and capture one frame per source
- `image.go` — shm pixel-format handling, output-transform, scaling, PNG output
- `proto/` — generated protocol bindings (+ `register.go`); see `generate.sh`
