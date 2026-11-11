// wlthumbs captures thumbnails of every open window (and optionally every
// monitor) over a single Wayland connection using the wlroots capture protocols
// (ext-foreign-toplevel-list-v1, ext-image-capture-source-v1, and
// ext-image-copy-capture-v1). It scales each frame in-process and writes a small
// PNG, printing one TSV row per source:
//
//	TYPE \t ID \t THUMBPATH \t APP \t TITLE
//
// where TYPE is "window" or "output". A failed capture still prints its row with
// an empty THUMBPATH so callers can show a label without an icon. The line-
// oriented output is meant to be joined/filtered by a shell caller (e.g. a rofi
// grid front-end).
package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

func main() {
	log.SetFlags(0)
	log.SetPrefix("wlthumbs: ")

	size := flag.Int("size", 256, "max thumbnail dimension in px")
	dir := flag.String("dir", "", "output directory for thumbnails (default: a temp dir under $XDG_RUNTIME_DIR)")
	windows := flag.Bool("windows", true, "capture windows (toplevels)")
	outputs := flag.Bool("outputs", false, "capture monitors (outputs)")
	ids := flag.String("ids", "", "comma-separated foreign toplevel IDs to capture; required for dock")
	flag.Parse()
	allowed := make(map[string]bool)
	for _, id := range strings.Split(*ids, ",") {
		if len(id) != 32 || strings.Trim(id, "0123456789abcdef") != "" {
			log.Fatal("invalid foreign toplevel identifier")
		}
		allowed[id] = true
	}
	if len(allowed) == 0 || len(allowed) > 8 || *outputs {
		log.Fatal("dock capture requires 1-8 window IDs and no output capture")
	}

	outDir, err := ensureDir(*dir)
	if err != nil {
		log.Fatal(err)
	}

	t := newTimer()
	a := &app{}
	if err := a.connect(); err != nil {
		log.Fatal(err)
	}
	defer a.display.Context().Close()
	t.mark("connect")

	a.enumerate()
	t.mark("enumerate")

	sources := a.buildSources(*windows, *outputs, allowed)
	t.mark("sources")

	a.capture(sources, outDir, *size)
	t.mark("capture+encode")

	for _, s := range sources {
		fmt.Printf("%s\t%s\t%s\t%s\t%s\n", s.typ, s.id, s.thumb, s.app, s.title)
	}
}

// buildSources creates a capture source for each requested window/monitor, in a
// stable order (windows then outputs).
func (a *app) buildSources(windows, outputs bool, allowed map[string]bool) []*source {
	var sources []*source
	if windows {
		for _, t := range a.toplevels {
			if t.closed || !allowed[t.id] {
				continue
			}
			src, err := a.toplevelSrcMgr.CreateSource(t.handle)
			if err != nil {
				log.Printf("create window source %q: %v", t.id, err)
				continue
			}
			sources = append(sources, &source{typ: "window", id: t.id, app: t.appID, title: t.title, cap: src})
		}
	}
	if outputs {
		for _, o := range a.outputs {
			src, err := a.outputSrcMgr.CreateSource(o.wl)
			if err != nil {
				log.Printf("create output source %q: %v", o.name, err)
				continue
			}
			model := strings.TrimSpace(o.make_ + " " + o.model)
			sources = append(sources, &source{typ: "output", id: o.name, app: model, title: o.name, cap: src})
		}
	}
	return sources
}

// capture grabs each source one at a time on the single connection (wlroots does
// not parallelize captures anyway) and hands the frame to a worker pool to scale
// + encode while the next window is captured — so encode cost hides under the
// compositor's capture time, and only one capture session is ever live at once.
func (a *app) capture(sources []*source, outDir string, size int) {
	var wg sync.WaitGroup
	sem := make(chan struct{}, max(2, runtime.NumCPU()))
	for _, s := range sources {
		if !a.captureOne(s) {
			continue
		}
		path := filepath.Join(outDir, safeName(s.id)+".png")
		wg.Add(1)
		sem <- struct{}{}
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			if err := writeThumb(s.raw, int(s.w), int(s.h), s.transform, s.swapRB, size, path); err != nil {
				log.Printf("thumb %s: %v", path, err)
				return
			}
			s.thumb = path
		}()
	}
	wg.Wait()
}

// safeName turns a source id into a filename. Foreign-toplevel ids and output
// names are filename-safe on sway; we only guard against path separators and
// control characters so a caller can build "$dir/$id.png" from the id alone.
func safeName(id string) string {
	return strings.Map(func(r rune) rune {
		if r == '/' || r < 0x20 {
			return '_'
		}
		return r
	}, id)
}

func ensureDir(dir string) (string, error) {
	if dir != "" {
		return dir, os.MkdirAll(dir, 0o700)
	}
	base := os.Getenv("XDG_RUNTIME_DIR")
	if base == "" {
		base = os.TempDir()
	}
	return os.MkdirTemp(base, "wlthumbs-")
}

// timer prints phase durations to stderr when WLTHUMBS_TIME is set.
type timer struct {
	on   bool
	last time.Time
}

func newTimer() *timer { return &timer{on: os.Getenv("WLTHUMBS_TIME") != "", last: time.Now()} }

func (t *timer) mark(label string) {
	if !t.on {
		return
	}
	now := time.Now()
	fmt.Fprintf(os.Stderr, "%-12s %6.1fms\n", label, float64(now.Sub(t.last).Microseconds())/1000)
	t.last = now
}
