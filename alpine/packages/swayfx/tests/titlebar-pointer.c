#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "pointer.h"

static struct zwlr_virtual_pointer_manager_v1 *manager;

static void global(void *data, struct wl_registry *registry, uint32_t name,
        const char *interface, uint32_t version) {
    (void)data;
    (void)version;
    if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name)) {
        manager = wl_registry_bind(registry, name,
            &zwlr_virtual_pointer_manager_v1_interface, 1);
    }
}

static void removed(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data;
    (void)registry;
    (void)name;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        return 1;
    }
    unsigned width = (unsigned)strtoul(argv[1], NULL, 10);
    unsigned height = (unsigned)strtoul(argv[2], NULL, 10);
    struct wl_display *display = wl_display_connect(NULL);
    if (!display || width == 0 || height == 0) {
        return 1;
    }
    struct wl_registry *registry = wl_display_get_registry(display);
    const struct wl_registry_listener listener = {global, removed};
    wl_registry_add_listener(registry, &listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !manager) {
        return 2;
    }
    struct zwlr_virtual_pointer_v1 *pointer =
        zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, NULL);
    if (wl_display_roundtrip(display) < 0) {
        return 2;
    }
    puts("ready");
    fflush(stdout);
    char command[128];
    unsigned first, second;
    while (fgets(command, sizeof command, stdin)) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        uint32_t stamp = (uint32_t)(now.tv_sec * 1000 + now.tv_nsec / 1000000);
        if (sscanf(command, "move %u %u", &first, &second) == 2) {
            zwlr_virtual_pointer_v1_motion_absolute(pointer, stamp,
                first, second, width, height);
        } else if (sscanf(command, "press %u", &first) == 1) {
            zwlr_virtual_pointer_v1_button(pointer, stamp, first, 1);
        } else if (sscanf(command, "release %u", &first) == 1) {
            zwlr_virtual_pointer_v1_button(pointer, stamp, first, 0);
        } else {
            return 3;
        }
        zwlr_virtual_pointer_v1_frame(pointer);
        if (wl_display_roundtrip(display) < 0) {
            return 4;
        }
        puts("ok");
        fflush(stdout);
    }
    zwlr_virtual_pointer_v1_destroy(pointer);
    wl_display_roundtrip(display);
    wl_display_disconnect(display);
    return 0;
}
