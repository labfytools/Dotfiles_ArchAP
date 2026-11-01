/* TEST_ONLY: offers two synthetic representations through the private
 * compositor's data-control protocol. Never connects to the user's display:
 * the Python harness supplies an isolated XDG_RUNTIME_DIR/WAYLAND_DISPLAY. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "data-control.h"
static struct wl_seat *seat;
static struct zwlr_data_control_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    (void)data; (void)version;
    if (!strcmp(interface,"wl_seat"))
        seat=wl_registry_bind(registry,name,&wl_seat_interface,1);
    if (!strcmp(interface,"zwlr_data_control_manager_v1"))
        manager=wl_registry_bind(registry,name,&zwlr_data_control_manager_v1_interface,1);
}
static void removed(void *d, struct wl_registry *r, uint32_t n) {(void)d;(void)r;(void)n;}
static const struct wl_registry_listener registry_listener={global,removed};
static void send_data(void *data, struct zwlr_data_control_source_v1 *source,
                      const char *mime, int32_t fd) {
    (void)data;(void)source;(void)mime;
    /* Payload is intentionally a harmless sentinel; only MIME routing is tested. */
    const char text[]="TEST_ONLY synthetic representation";
    (void)write(fd,text,sizeof(text)-1); close(fd);
}
static void cancelled(void *d, struct zwlr_data_control_source_v1 *s) {(void)d;(void)s;}
static const struct zwlr_data_control_source_v1_listener source_listener={send_data,cancelled};
int main(void) {
    struct wl_display *display=wl_display_connect(NULL);
    if (!display) return 1;
    struct wl_registry *registry=wl_display_get_registry(display);
    wl_registry_add_listener(registry,&registry_listener,NULL);
    if (wl_display_roundtrip(display)<0 || !seat || !manager) return 2;
    struct zwlr_data_control_source_v1 *source=zwlr_data_control_manager_v1_create_data_source(manager);
    zwlr_data_control_source_v1_add_listener(source,&source_listener,NULL);
    zwlr_data_control_source_v1_offer(source,"text/plain");
    zwlr_data_control_source_v1_offer(source,"image/png");
    struct zwlr_data_control_device_v1 *device=zwlr_data_control_manager_v1_get_data_device(manager,seat);
    zwlr_data_control_device_v1_set_selection(device,source);
    while (wl_display_dispatch(display)>=0) {}
    wl_display_disconnect(display); return 0;
}
