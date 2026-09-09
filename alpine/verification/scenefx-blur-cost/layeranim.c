/* layeranim - a minimal wlr-layer-shell client that damages a rectangle at a
 * controlled rate on a controlled layer.  Used only to measure a compositor.
 * Nothing here is installed; it exists to produce a number. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/timerfd.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include "xdg-shell-client-protocol.h"

static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct zwlr_layer_shell_v1 *layer_shell;
static struct wl_output *output;
static struct wl_surface *surface;
static struct zwlr_layer_surface_v1 *layer_surface;
static struct wl_buffer *buffer;
static uint32_t *pixels;
static int surf_w, surf_h;          /* logical size given by configure */
static int buf_w, buf_h;            /* buffer size = logical * scale */
static int scale = 1;
static bool configured = false;
static long commits = 0, frames = 0;

static bool callback_mode = false;
static bool pending_frame = false;
static void paint_and_commit(void);
static void frame_done(void *d, struct wl_callback *cb, uint32_t t) {
	(void)d; (void)t; frames++; wl_callback_destroy(cb); pending_frame = false;
	if (callback_mode) paint_and_commit();
}
static const struct wl_callback_listener frame_listener = { .done = frame_done };

static void ls_configure(void *d, struct zwlr_layer_surface_v1 *ls,
		uint32_t serial, uint32_t w, uint32_t h) {
	(void)d;
	zwlr_layer_surface_v1_ack_configure(ls, serial);
	surf_w = (int)w; surf_h = (int)h;
	configured = true;
}
static void ls_closed(void *d, struct zwlr_layer_surface_v1 *ls) { (void)d; (void)ls; exit(0); }
static const struct zwlr_layer_surface_v1_listener ls_listener = {
	.configure = ls_configure, .closed = ls_closed,
};

static void handle_global(void *data, struct wl_registry *reg, uint32_t name,
		const char *iface, uint32_t ver) {
	(void)data; (void)ver;
	if (!strcmp(iface, wl_compositor_interface.name))
		compositor = wl_registry_bind(reg, name, &wl_compositor_interface, 4);
	else if (!strcmp(iface, wl_shm_interface.name))
		shm = wl_registry_bind(reg, name, &wl_shm_interface, 1);
	else if (!strcmp(iface, zwlr_layer_shell_v1_interface.name))
		layer_shell = wl_registry_bind(reg, name, &zwlr_layer_shell_v1_interface, 4);
	else if (!strcmp(iface, wl_output_interface.name) && !output)
		output = wl_registry_bind(reg, name, &wl_output_interface, 2);
}
static void handle_global_remove(void *d, struct wl_registry *r, uint32_t n) { (void)d;(void)r;(void)n; }
static const struct wl_registry_listener registry_listener = {
	.global = handle_global, .global_remove = handle_global_remove,
};

static int anon_shm(size_t size) {
	char name[] = "/layeranim-XXXXXX";
	for (int i = 0; i < 100; i++) {
		struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
		long r = ts.tv_nsec + i;
		for (int j = 0; j < 6; j++) { name[11 + j] = 'A' + (r % 26); r /= 26; }
		int fd = shm_open(name, O_RDWR | O_CREAT | O_EXCL, 0600);
		if (fd >= 0) { shm_unlink(name); if (ftruncate(fd, size) < 0) { close(fd); return -1; } return fd; }
		if (errno != EEXIST) return -1;
	}
	return -1;
}

static int g_dw, g_dh; static bool g_full = false; static unsigned g_step = 0;
static void paint_and_commit(void) {
	int x = g_full ? 0 : (int)((g_step * 37) % (buf_w - g_dw + 1));
	int y = g_full ? 0 : (int)((g_step * 53) % (buf_h - g_dh + 1));
	uint32_t colour = 0x30000000u | ((g_step * 7919u) & 0x00ffffffu);
	for (int row = 0; row < g_dh; row++) {
		uint32_t *p = pixels + (size_t)(y + row) * buf_w + x;
		for (int col = 0; col < g_dw; col++) p[col] = colour;
	}
	wl_surface_attach(surface, buffer, 0, 0);
	wl_surface_damage_buffer(surface, x, y, g_dw, g_dh);
	struct wl_callback *c = wl_surface_frame(surface);
	wl_callback_add_listener(c, &frame_listener, NULL);
	wl_surface_commit(surface);
	pending_frame = true;
	commits++; g_step++;
}

int main(int argc, char **argv) {
	const char *layer_name = "bottom", *ns = "measure-anim";
	double rate = 60.0, duration = 10.0;
	int dmg_w = 200, dmg_h = 200; bool dmg_full = false;
	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--layer") && i + 1 < argc) layer_name = argv[++i];
		else if (!strcmp(argv[i], "--mode") && i + 1 < argc) callback_mode = !strcmp(argv[++i], "callback");
		else if (!strcmp(argv[i], "--namespace") && i + 1 < argc) ns = argv[++i];
		else if (!strcmp(argv[i], "--rate") && i + 1 < argc) rate = atof(argv[++i]);
		else if (!strcmp(argv[i], "--duration") && i + 1 < argc) duration = atof(argv[++i]);
		else if (!strcmp(argv[i], "--damage") && i + 1 < argc) {
			const char *v = argv[++i];
			if (!strcmp(v, "full")) dmg_full = true;
			else sscanf(v, "%dx%d", &dmg_w, &dmg_h);
		}
	}
	enum zwlr_layer_shell_v1_layer layer = ZWLR_LAYER_SHELL_V1_LAYER_BOTTOM;
	if (!strcmp(layer_name, "background")) layer = ZWLR_LAYER_SHELL_V1_LAYER_BACKGROUND;
	else if (!strcmp(layer_name, "top")) layer = ZWLR_LAYER_SHELL_V1_LAYER_TOP;
	else if (!strcmp(layer_name, "overlay")) layer = ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY;

	struct wl_display *dpy = wl_display_connect(NULL);
	if (!dpy) { fprintf(stderr, "no display\n"); return 1; }
	struct wl_registry *reg = wl_display_get_registry(dpy);
	wl_registry_add_listener(reg, &registry_listener, NULL);
	wl_display_roundtrip(dpy);
	if (!compositor || !shm || !layer_shell) { fprintf(stderr, "missing globals\n"); return 1; }

	surface = wl_compositor_create_surface(compositor);
	struct wl_region *empty = wl_compositor_create_region(compositor);
	wl_surface_set_input_region(surface, empty);
	wl_region_destroy(empty);

	layer_surface = zwlr_layer_shell_v1_get_layer_surface(layer_shell, surface, output, layer, ns);
	zwlr_layer_surface_v1_add_listener(layer_surface, &ls_listener, NULL);
	zwlr_layer_surface_v1_set_anchor(layer_surface,
		ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP | ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM |
		ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT | ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT);
	zwlr_layer_surface_v1_set_exclusive_zone(layer_surface, 0);
	zwlr_layer_surface_v1_set_keyboard_interactivity(layer_surface,
		ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE);
	wl_surface_commit(surface);
	wl_display_roundtrip(dpy);
	if (!configured) { fprintf(stderr, "no configure\n"); return 1; }

	/* Match the buffer to the output scale the compositor is using so the
	 * surface really covers the physical output. */
	const char *sc = getenv("LAYERANIM_SCALE");
	scale = sc ? atoi(sc) : 1; if (scale < 1) scale = 1;
	buf_w = surf_w * scale; buf_h = surf_h * scale;
	size_t stride = (size_t)buf_w * 4, size = stride * buf_h;
	int fd = anon_shm(size);
	if (fd < 0) { fprintf(stderr, "shm failed\n"); return 1; }
	pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (pixels == MAP_FAILED) { fprintf(stderr, "mmap failed\n"); return 1; }
	struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
	buffer = wl_shm_pool_create_buffer(pool, 0, buf_w, buf_h, stride, WL_SHM_FORMAT_ARGB8888);
	wl_shm_pool_destroy(pool); close(fd);
	/* mostly transparent, like an edges overlay would be */
	for (size_t i = 0; i < size / 4; i++) pixels[i] = 0x00000000;
	wl_surface_set_buffer_scale(surface, scale);
	wl_surface_attach(surface, buffer, 0, 0);
	wl_surface_damage_buffer(surface, 0, 0, buf_w, buf_h);
	struct wl_callback *cb = wl_surface_frame(surface);
	wl_callback_add_listener(cb, &frame_listener, NULL);
	wl_surface_commit(surface);
	wl_display_roundtrip(dpy);

	int tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC);
	long period_ns = rate > 0 ? (long)(1e9 / rate) : 1000000L;
	struct itimerspec its = {
		.it_interval = { .tv_sec = period_ns / 1000000000L, .tv_nsec = period_ns % 1000000000L },
		.it_value    = { .tv_sec = period_ns / 1000000000L, .tv_nsec = period_ns % 1000000000L },
	};
	timerfd_settime(tfd, 0, &its, NULL);

	struct timespec t0; clock_gettime(CLOCK_MONOTONIC, &t0);
	g_dw = dmg_full ? buf_w : dmg_w * scale; g_dh = dmg_full ? buf_h : dmg_h * scale;
	if (g_dw > buf_w) g_dw = buf_w;
	if (g_dh > buf_h) g_dh = buf_h;
	g_full = dmg_full;
	struct pollfd pfds[2] = { { .fd = wl_display_get_fd(dpy), .events = POLLIN }, { .fd = tfd, .events = POLLIN } };
	if (callback_mode) paint_and_commit();
	while (1) {
		struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
		double el = (now.tv_sec - t0.tv_sec) + (now.tv_nsec - t0.tv_nsec) / 1e9;
		if (el >= duration) break;
		wl_display_flush(dpy);
		if (poll(pfds, callback_mode ? 1 : 2, 100) < 0) break;
		if (pfds[0].revents & POLLIN) { if (wl_display_dispatch(dpy) < 0) break; }
		if (!callback_mode && (pfds[1].revents & POLLIN)) {
			uint64_t exp; ssize_t r = read(tfd, &exp, sizeof(exp)); (void)r;
			paint_and_commit();
		}
	}
	wl_display_flush(dpy);
	struct timespec te; clock_gettime(CLOCK_MONOTONIC, &te);
	double tot = (te.tv_sec - t0.tv_sec) + (te.tv_nsec - t0.tv_nsec) / 1e9;
	printf("{\"commits\": %ld, \"frame_callbacks\": %ld, \"elapsed\": %.3f, \"commit_hz\": %.2f, \"buffer\": \"%dx%d\", \"damage\": \"%dx%d\", \"layer\": \"%s\", \"mode\": \"%s\"}\n",
		commits, frames, tot, tot > 0 ? commits / tot : 0.0, buf_w, buf_h, g_dw, g_dh, layer_name,
		callback_mode ? "callback" : "timer");
	return 0;
}
