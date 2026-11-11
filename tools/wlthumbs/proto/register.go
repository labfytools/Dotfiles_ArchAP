package proto

import (
	"reflect"
	"unsafe"

	"github.com/rajveermalviya/go-wayland/wayland/client"
)

// registerServerObject registers a proxy under a server-allocated object id.
//
// go-wayland only knows how to create client-allocated objects (its Context has
// no public way to register an object under an id chosen by the compositor). But
// the ext_foreign_toplevel_list_v1.toplevel event delivers a new_id the *server*
// allocates, and the object must be registered under that id for its subsequent
// events (identifier/title/app_id/closed/done) to be dispatched to it. We reach
// into the Context's private objects map to do so. This is safe because the
// go-wayland dependency is version-pinned, so its internal layout is fixed.
func registerServerObject(ctx *client.Context, id uint32, p client.Proxy) {
	p.SetContext(ctx)
	p.SetID(id)
	f := reflect.ValueOf(ctx).Elem().FieldByName("objects")
	f = reflect.NewAt(f.Type(), unsafe.Pointer(f.UnsafeAddr())).Elem()
	f.SetMapIndex(reflect.ValueOf(id), reflect.ValueOf(p))
}
