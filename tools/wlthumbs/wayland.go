package main

import (
	"fmt"
	"log"
	"strings"

	"github.com/mil-ad/wlthumbs/proto"
	"github.com/rajveermalviya/go-wayland/wayland/client"
	"golang.org/x/sys/unix"
)

type toplevel struct {
	handle           *proto.ExtForeignToplevelHandle
	id, title, appID string
	closed, done     bool
}

type output struct {
	wl           *client.Output
	name         string
	make_, model string
	done         bool
}

// source is a normalized capture target (window or monitor). captureOne fills
// the trailing fields with the captured frame.
type source struct {
	typ   string // "window" | "output"
	id    string
	app   string
	title string
	cap   *proto.ExtImageCaptureSource

	raw       []byte // captured pixels (nil until/unless capture succeeds)
	w, h      uint32
	transform uint32
	swapRB    bool
	thumb     string // path to the written PNG (empty if capture/encode failed)
}

// app holds the Wayland connection and the globals/objects we bind on it.
type app struct {
	display        *client.Display
	registry       *client.Registry
	shm            *client.Shm
	copyMgr        *proto.ExtImageCopyCaptureManager
	toplevelSrcMgr *proto.ExtForeignToplevelImageCaptureSourceManager
	outputSrcMgr   *proto.ExtOutputImageCaptureSourceManager
	toplevelList   *proto.ExtForeignToplevelList

	toplevels []*toplevel
	outputs   []*output
}

// connect opens the Wayland connection, binds the globals we need, and verifies
// the compositor supports the required capture protocols.
func (a *app) connect() error {
	display, err := client.Connect("")
	if err != nil {
		return fmt.Errorf("connect to wayland: %w", err)
	}
	a.display = display
	display.SetErrorHandler(func(e client.DisplayErrorEvent) {
		log.Printf("display error: object=%d code=%d %q", e.ObjectId, e.Code, e.Message)
	})

	registry, err := display.GetRegistry()
	if err != nil {
		return fmt.Errorf("get registry: %w", err)
	}
	a.registry = registry
	registry.SetGlobalHandler(a.handleGlobal)

	a.roundtrip() // register globals
	a.roundtrip() // deliver their initial events

	var missing []string
	if a.shm == nil {
		missing = append(missing, "wl_shm")
	}
	if a.copyMgr == nil {
		missing = append(missing, "ext_image_copy_capture_manager_v1")
	}
	if a.toplevelSrcMgr == nil {
		missing = append(missing, "ext_foreign_toplevel_image_capture_source_manager_v1")
	}
	if len(missing) > 0 {
		return fmt.Errorf("compositor is missing required protocols: %s", strings.Join(missing, ", "))
	}
	return nil
}

func (a *app) ctx() *client.Context { return a.display.Context() }

// bind is a spec-correct wl_registry.bind. go-wayland's Registry.Bind writes the
// string-length prefix as the *padded* length instead of len+1; older libwayland
// tolerated it, but newer libwayland rejects it with "invalid arguments". The
// proxy is already registered by its New* constructor, so we only marshal and
// send the request here.
func (a *app) bind(e client.RegistryGlobalEvent, p client.Proxy) {
	iface := e.Interface
	strLen := len(iface) + 1 // includes the null terminator
	pad := strLen
	if pad%4 != 0 {
		pad += 4 - pad%4
	}
	const opcode = 0
	bufLen := 8 + 4 + (4 + pad) + 4 + 4
	buf := make([]byte, bufLen)
	client.PutUint32(buf[0:4], a.registry.ID())
	client.PutUint32(buf[4:8], uint32(bufLen<<16|opcode))
	client.PutUint32(buf[8:12], e.Name)
	client.PutString(buf[12:12+4+pad], iface, strLen)
	o := 12 + 4 + pad
	client.PutUint32(buf[o:o+4], e.Version)
	client.PutUint32(buf[o+4:o+8], p.ID())
	if err := a.ctx().WriteMsg(buf, nil); err != nil {
		log.Fatalf("bind %s: %v", iface, err)
	}
}

func (a *app) handleGlobal(e client.RegistryGlobalEvent) {
	switch e.Interface {
	case "wl_shm":
		a.shm = client.NewShm(a.ctx())
		a.bind(e, a.shm)
	case "ext_image_copy_capture_manager_v1":
		a.copyMgr = proto.NewExtImageCopyCaptureManager(a.ctx())
		a.bind(e, a.copyMgr)
	case "ext_foreign_toplevel_image_capture_source_manager_v1":
		a.toplevelSrcMgr = proto.NewExtForeignToplevelImageCaptureSourceManager(a.ctx())
		a.bind(e, a.toplevelSrcMgr)
	case "ext_output_image_capture_source_manager_v1":
		a.outputSrcMgr = proto.NewExtOutputImageCaptureSourceManager(a.ctx())
		a.bind(e, a.outputSrcMgr)
	case "ext_foreign_toplevel_list_v1":
		a.toplevelList = proto.NewExtForeignToplevelList(a.ctx())
		a.bind(e, a.toplevelList)
		a.toplevelList.SetToplevelHandler(a.handleToplevel)
	case "wl_output":
		o := &output{wl: client.NewOutput(a.ctx())}
		a.bind(e, o.wl)
		a.outputs = append(a.outputs, o)
		o.wl.SetGeometryHandler(func(e client.OutputGeometryEvent) { o.make_, o.model = e.Make, e.Model })
		o.wl.SetNameHandler(func(e client.OutputNameEvent) { o.name = e.Name })
		o.wl.SetDoneHandler(func(client.OutputDoneEvent) { o.done = true })
	}
}

func (a *app) handleToplevel(e proto.ExtForeignToplevelListToplevelEvent) {
	t := &toplevel{handle: e.Toplevel}
	a.toplevels = append(a.toplevels, t)
	t.handle.SetIdentifierHandler(func(e proto.ExtForeignToplevelHandleIdentifierEvent) { t.id = e.Identifier })
	t.handle.SetTitleHandler(func(e proto.ExtForeignToplevelHandleTitleEvent) { t.title = e.Title })
	t.handle.SetAppIdHandler(func(e proto.ExtForeignToplevelHandleAppIdEvent) { t.appID = e.AppId })
	t.handle.SetClosedHandler(func(proto.ExtForeignToplevelHandleClosedEvent) { t.closed = true })
	t.handle.SetDoneHandler(func(proto.ExtForeignToplevelHandleDoneEvent) { t.done = true })
}

// enumerate collects toplevels and outputs, round-tripping until each has
// delivered its full initial state (a "done" event) and no new ones appear.
func (a *app) enumerate() {
	const maxRounds = 20 // safety bound; converges in 1-2 in practice
	for range maxRounds {
		before := len(a.toplevels)
		a.roundtrip()
		stable := len(a.toplevels) == before
		allDone := true
		for _, t := range a.toplevels {
			if !t.done && !t.closed {
				allDone = false
			}
		}
		for _, o := range a.outputs {
			if !o.done {
				allDone = false
			}
		}
		if stable && allDone {
			return
		}
	}
}

// roundtrip flushes the connection and dispatches events until the compositor
// answers a sync callback, i.e. until everything queued so far is processed.
func (a *app) roundtrip() {
	cb, err := a.display.Sync()
	if err != nil {
		log.Fatalf("sync: %v", err)
	}
	defer cb.Destroy()
	done := false
	cb.SetDoneHandler(func(client.CallbackDoneEvent) { done = true })
	for !done {
		if err := a.dispatch(); err != nil {
			log.Fatalf("dispatch: %v", err)
		}
	}
}

// dispatch processes one event, tolerating events addressed to objects we have
// already destroyed. The compositor may have queued events for a session/frame
// before it saw our destroy request; go-wayland reports those as "unable find
// sender" but has still consumed the message, so it is safe to continue. A real
// connection failure (EOF, broken pipe) is returned so callers can abort.
func (a *app) dispatch() error {
	err := a.ctx().Dispatch()
	if err != nil && strings.Contains(err.Error(), "unable find sender") {
		return nil
	}
	return err
}

// captureOne grabs a single frame for one source into an shm buffer and stores
// the raw pixels (and dimensions/transform/format) on the source. It returns
// false if the compositor could not satisfy the capture. All Wayland and mmap
// resources for this source are released before returning.
func (a *app) captureOne(s *source) bool {
	session, err := a.copyMgr.CreateSession(s.cap, 0)
	if err != nil {
		log.Printf("create session %q: %v", s.id, err)
		return false
	}
	defer session.Destroy()
	defer s.cap.Destroy()

	var w, h uint32
	var formats []uint32
	sessionDone := false
	session.SetBufferSizeHandler(func(e proto.ExtImageCopyCaptureSessionBufferSizeEvent) { w, h = e.Width, e.Height })
	session.SetShmFormatHandler(func(e proto.ExtImageCopyCaptureSessionShmFormatEvent) { formats = append(formats, e.Format) })
	session.SetDoneHandler(func(proto.ExtImageCopyCaptureSessionDoneEvent) { sessionDone = true })
	session.SetStoppedHandler(func(proto.ExtImageCopyCaptureSessionStoppedEvent) { sessionDone = true })

	a.roundtrip()
	if !sessionDone || w == 0 || h == 0 {
		log.Printf("no buffer constraints for %q", s.id)
		return false
	}

	format, swapRB, ok := chooseFormat(formats)
	if !ok {
		log.Printf("no supported shm format for %q (got %v)", s.id, formats)
		return false
	}

	stride := int(w) * 4
	size := stride * int(h)
	fd, err := shmFile(size)
	if err != nil {
		log.Printf("shm file for %q: %v", s.id, err)
		return false
	}
	defer unix.Close(fd)

	data, err := unix.Mmap(fd, 0, size, unix.PROT_READ|unix.PROT_WRITE, unix.MAP_SHARED)
	if err != nil {
		log.Printf("mmap for %q: %v", s.id, err)
		return false
	}
	defer unix.Munmap(data)

	pool, err := a.shm.CreatePool(fd, int32(size))
	if err != nil {
		log.Printf("create pool for %q: %v", s.id, err)
		return false
	}
	defer pool.Destroy()

	buf, err := pool.CreateBuffer(0, int32(w), int32(h), int32(stride), uint32(format))
	if err != nil {
		log.Printf("create buffer for %q: %v", s.id, err)
		return false
	}
	defer buf.Destroy()

	frame, err := session.CreateFrame()
	if err != nil {
		log.Printf("create frame for %q: %v", s.id, err)
		return false
	}
	defer frame.Destroy()

	var tf uint32
	ready, failed := false, false
	frame.SetTransformHandler(func(e proto.ExtImageCopyCaptureFrameTransformEvent) { tf = e.Transform })
	frame.SetReadyHandler(func(proto.ExtImageCopyCaptureFrameReadyEvent) { ready = true })
	frame.SetFailedHandler(func(e proto.ExtImageCopyCaptureFrameFailedEvent) {
		failed = true
		log.Printf("capture failed for %q (reason=%d)", s.id, e.Reason)
	})

	if err := frame.AttachBuffer(buf); err != nil {
		log.Printf("attach buffer for %q: %v", s.id, err)
		return false
	}
	frame.DamageBuffer(0, 0, int32(w), int32(h))
	if err := frame.Capture(); err != nil {
		log.Printf("capture for %q: %v", s.id, err)
		return false
	}

	for !ready && !failed {
		if err := a.dispatch(); err != nil {
			log.Printf("dispatch during capture %q: %v", s.id, err)
			return false
		}
	}
	if failed {
		return false
	}

	// Copy the pixels out of the mapping before the deferred Munmap runs.
	s.raw = make([]byte, size)
	copy(s.raw, data)
	s.w, s.h, s.transform, s.swapRB = w, h, tf, swapRB
	return true
}

// shmFile returns an fd backed by an anonymous in-memory file of the given size.
func shmFile(size int) (int, error) {
	fd, err := unix.MemfdCreate("wlthumbs", unix.MFD_CLOEXEC)
	if err != nil {
		return -1, fmt.Errorf("memfd_create: %w", err)
	}
	if err := unix.Ftruncate(fd, int64(size)); err != nil {
		unix.Close(fd)
		return -1, fmt.Errorf("ftruncate: %w", err)
	}
	return fd, nil
}
