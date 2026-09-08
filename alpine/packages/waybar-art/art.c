/* SPDX-License-Identifier: MIT */
#include "waybar_cffi_module.h"
#include "help.h"
#include <fcntl.h>
#include <glob.h>
#include <json-glib/json-glib.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

const size_t wbcffi_version = 2;

/* Logical height of the painting badge inside the 32px bar. */
#define THUMBNAIL_HEIGHT 22
#define CURRENT_WALLPAPER "current-wallpaper.png"

typedef struct {
    GtkWidget *box;
    GtkWidget *content;
    GtkWidget *label;
    GtkWidget *image;
    char *command;
    char *thumbnail;
    gboolean generating;
    GFileMonitor *monitor;
    guint monitor_timer;
    guint timer;
    guint refs;
    gboolean disposed;
    GSubprocess *status;
    gint64 started;
    double scroll;
    void *help;
} Artwork;

static void release(Artwork *art) {
    if (--art->refs == 0) {
        g_free(art->command);
        g_free(art->thumbnail);
        g_free(art);
    }
}

typedef struct {
    gboolean shift;
    gboolean super;
} Modifiers;

static gboolean key_pressed(const unsigned char *keys, unsigned int key) {
    return keys[key / 8] & (1u << (key % 8));
}

static gboolean is_keyboard(int fd) {
    unsigned char keys[(KEY_MAX + 8) / 8] = {0};
    return ioctl(fd, EVIOCGBIT(EV_KEY, sizeof keys), keys) >= 0 &&
           key_pressed(keys, KEY_A) && key_pressed(keys, KEY_ENTER) &&
           key_pressed(keys, KEY_SPACE);
}

/* Layer-shell panels usually have no keyboard focus, and therefore receive
 * GDK modifier state zero. Query one kernel key snapshot per device at the
 * button callback. Never read input events, retain key history, or ask for
 * privileged input access here. */
static Modifiers modifiers_pressed(guint state) {
    Modifiers result = {
        .shift = (state & GDK_SHIFT_MASK) != 0,
        .super = (state & (GDK_MOD4_MASK | GDK_SUPER_MASK)) != 0,
    };
    if (result.shift && result.super) return result;
    glob_t devices = {0};
    if (glob("/dev/input/event*", 0, NULL, &devices) == 0) {
        for (size_t i = 0; i < devices.gl_pathc && !(result.shift && result.super); ++i) {
            int fd = open(devices.gl_pathv[i], O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
            if (fd < 0) continue;
            struct stat info;
            unsigned char keys[(KEY_MAX + 8) / 8] = {0};
            if (fstat(fd, &info) == 0 && S_ISCHR(info.st_mode) && is_keyboard(fd) &&
                    ioctl(fd, EVIOCGKEY(sizeof keys), keys) >= 0) {
                result.shift = result.shift || key_pressed(keys, KEY_LEFTSHIFT) ||
                               key_pressed(keys, KEY_RIGHTSHIFT);
                result.super = result.super || key_pressed(keys, KEY_LEFTMETA) ||
                               key_pressed(keys, KEY_RIGHTMETA);
            }
            close(fd);
        }
    }
    globfree(&devices);
    return result;
}

static const char *string_member(JsonObject *object, const char *name) {
    JsonNode *node = json_object_get_member(object, name);
    return node && JSON_NODE_HOLDS_VALUE(node) && json_node_get_value_type(node) == G_TYPE_STRING
        ? json_node_get_string(node) : NULL;
}

static int thumbnail_scale(Artwork *art) {
    int scale = gtk_widget_get_scale_factor(art->content);
    return scale > 0 ? scale : 1;
}

static void clear_thumbnail(Artwork *art) {
    g_clear_pointer(&art->thumbnail, g_free);
    gtk_image_clear(GTK_IMAGE(art->image));
}

/* The status helper hands back a small cached PNG already scaled for this
 * panel's scale factor; the surface keeps it crisp on a HiDPI bar. Decoding a
 * thumbnail is trivial, so it happens inline unlike the painting itself. */
static void load_thumbnail(Artwork *art, const char *path) {
    if (g_strcmp0(path, art->thumbnail) == 0) return;
    GError *error = NULL;
    GdkPixbuf *pixbuf = gdk_pixbuf_new_from_file(path, &error);
    if (!pixbuf) {
        g_debug("Artwork thumbnail unavailable: %s", error ? error->message : path);
        g_clear_error(&error);
        clear_thumbnail(art);
        return;
    }
    cairo_surface_t *surface = gdk_cairo_surface_create_from_pixbuf(
        pixbuf, thumbnail_scale(art), gtk_widget_get_window(art->image));
    gtk_image_set_from_surface(GTK_IMAGE(art->image), surface);
    cairo_surface_destroy(surface);
    g_object_unref(pixbuf);
    g_free(art->thumbnail);
    art->thumbnail = g_strdup(path);
}

static void show_badge(Artwork *art) {
    gboolean picture = art->thumbnail != NULL && !art->generating;
    gtk_widget_set_visible(art->image, picture);
    gtk_widget_set_visible(art->label, !picture);
}

static void display_status(Artwork *art, const char *output) {
    JsonParser *parser = json_parser_new();
    if (json_parser_load_from_data(parser, output, -1, NULL) &&
            JSON_NODE_HOLDS_OBJECT(json_parser_get_root(parser))) {
        JsonObject *object = json_node_get_object(json_parser_get_root(parser));
        const char *text = string_member(object, "text");
        const char *tooltip = string_member(object, "tooltip");
        const char *state = string_member(object, "class");
        const char *thumbnail = string_member(object, "thumbnail");
        if (text) gtk_label_set_text(GTK_LABEL(art->label), text);
        if (tooltip) gtk_widget_set_tooltip_markup(art->box, tooltip);
        GtkStyleContext *style = gtk_widget_get_style_context(art->content);
        const char *classes[] = {"rotating", "paused", "generating"};
        for (size_t i = 0; i < G_N_ELEMENTS(classes); ++i) {
            gtk_style_context_remove_class(style, classes[i]);
            if (g_strcmp0(state, classes[i]) == 0) gtk_style_context_add_class(style, classes[i]);
        }
        art->generating = g_strcmp0(state, "generating") == 0;
        if (thumbnail && *thumbnail) load_thumbnail(art, thumbnail);
        else clear_thumbnail(art);
        show_badge(art);
    }
    g_object_unref(parser);
}

static void status_ready(GObject *source, GAsyncResult *result, gpointer data) {
    Artwork *art = data;
    char *output = NULL;
    if (g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result, &output, NULL, NULL) &&
            !art->disposed && g_subprocess_get_successful(G_SUBPROCESS(source)) && output) {
        display_status(art, output);
    }
    g_free(output);
    g_clear_object(&art->status);
    release(art);
}

static gboolean refresh_status(gpointer data) {
    Artwork *art = data;
    if (art->status) {
        if (g_get_monotonic_time() - art->started > 3 * G_TIME_SPAN_SECOND)
            g_subprocess_force_exit(art->status);
        return G_SOURCE_CONTINUE;
    }
    char height[16];
    g_snprintf(height, sizeof height, "%d", THUMBNAIL_HEIGHT * thumbnail_scale(art));
    art->status = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                                  NULL, art->command, "status", "--thumbnail-height", height, NULL);
    if (art->status) {
        art->started = g_get_monotonic_time();
        ++art->refs;
        g_subprocess_communicate_utf8_async(art->status, NULL, NULL, status_ready, art);
    }
    return G_SOURCE_CONTINUE;
}

static gboolean refresh_soon(gpointer data) {
    Artwork *art = data;
    art->monitor_timer = 0;
    refresh_status(art);
    return G_SOURCE_REMOVE;
}

/* The gallery replaces the current-wallpaper link atomically; coalesce the
 * burst of directory events into one status refresh so the badge follows a
 * painting change without waiting for the periodic poll. */
static void wallpaper_changed(GFileMonitor *monitor, GFile *file, GFile *other, GFileMonitorEvent event,
                              gpointer data) {
    (void)monitor;
    (void)event;
    Artwork *art = data;
    gboolean relevant = FALSE;
    GFile *candidates[] = {file, other};
    for (size_t i = 0; i < G_N_ELEMENTS(candidates) && !relevant; ++i) {
        if (!candidates[i]) continue;
        char *name = g_file_get_basename(candidates[i]);
        relevant = g_strcmp0(name, CURRENT_WALLPAPER) == 0;
        g_free(name);
    }
    if (!relevant || art->disposed) return;
    if (art->monitor_timer) g_source_remove(art->monitor_timer);
    art->monitor_timer = g_timeout_add(150, refresh_soon, art);
}

static void scale_changed(GObject *object, GParamSpec *spec, gpointer data) {
    (void)object;
    (void)spec;
    Artwork *art = data;
    /* A new scale needs a differently sized thumbnail; forget the current one. */
    g_clear_pointer(&art->thumbnail, g_free);
    refresh_status(art);
}

static void action(Artwork *art, const char *name) {
    GError *error = NULL;
    GSubprocess *process = g_subprocess_new(G_SUBPROCESS_FLAGS_NONE, &error, art->command, name, NULL);
    if (process) {
        g_object_unref(process);
    } else {
        g_warning("Artwork action failed: %s", error->message);
        gtk_widget_set_tooltip_text(art->box, error->message);
        g_error_free(error);
    }
    refresh_status(art);
}

static gboolean clicked(GtkWidget *widget, GdkEventButton *event, gpointer data) {
    (void)widget;
    /* GTK emits an additional double/triple event after a regular press. */
    if (event->type != GDK_BUTTON_PRESS) return TRUE;
    Artwork *art = data;
    if (event->button == 1) {
        Modifiers modifiers = modifiers_pressed(event->state);
        action(art, modifiers.super && modifiers.shift ? "new-theme" :
                    modifiers.shift ? "edit-prompts" : modifiers.super ? "generate" : "pick");
    }
    else if (event->button == 2) action(art, "pause");
    else if (event->button == 3) {
        Modifiers modifiers = modifiers_pressed(event->state);
        action(art, modifiers.super && modifiers.shift ? "prompt-theme" : "next");
    }
    return TRUE;
}

static gboolean scrolled(GtkWidget *widget, GdkEventScroll *event, gpointer data) {
    (void)widget;
    Artwork *art = data;
    if (event->direction == GDK_SCROLL_UP) action(art, "prev");
    else if (event->direction == GDK_SCROLL_DOWN) action(art, "next");
    else if (event->direction == GDK_SCROLL_SMOOTH) {
        art->scroll += event->delta_y;
        if (art->scroll >= 1 || art->scroll <= -1) {
            action(art, art->scroll < 0 ? "prev" : "next");
            art->scroll = 0;
        }
    }
    return TRUE;
}

static gboolean crossed(GtkWidget *widget, GdkEventCrossing *event, gpointer data) {
    (void)widget;
    Artwork *art = data;
    if (event->type == GDK_ENTER_NOTIFY)
        gtk_widget_set_state_flags(art->content, GTK_STATE_FLAG_PRELIGHT, FALSE);
    else
        gtk_widget_unset_state_flags(art->content, GTK_STATE_FLAG_PRELIGHT);
    return FALSE;
}

void *wbcffi_init(const wbcffi_init_info *info, const wbcffi_config_entry *entries, size_t count) {
    Artwork *art = g_new0(Artwork, 1);
    art->refs = 1;
    art->command = g_build_filename(g_get_home_dir(), ".local", "bin", "oldbook-wallpaper", NULL);
    for (size_t i = 0; i < count; ++i) {
        if (g_strcmp0(entries[i].key, "command") != 0) continue;
        JsonParser *parser = json_parser_new();
        if (json_parser_load_from_data(parser, entries[i].value, -1, NULL)) {
            JsonNode *node = json_parser_get_root(parser);
            if (JSON_NODE_HOLDS_VALUE(node) && json_node_get_value_type(node) == G_TYPE_STRING) {
                const char *command = json_node_get_string(node);
                if (g_path_is_absolute(command)) {
                    g_free(art->command);
                    art->command = g_strdup(command);
                }
            }
        }
        g_object_unref(parser);
    }
    art->box = gtk_event_box_new();
    /* The badge is a box so the glyph and the painting thumbnail share one
     * styled #custom-art surface; only one of them is visible at a time. */
    art->content = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_name(art->content, "custom-art");
    gtk_style_context_add_class(gtk_widget_get_style_context(art->content), "module");
    art->label = gtk_label_new("󰸉");
    art->image = gtk_image_new();
    gtk_style_context_add_class(gtk_widget_get_style_context(art->image), "thumbnail");
    gtk_widget_set_valign(art->image, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(art->label, GTK_ALIGN_CENTER);
    gtk_box_pack_start(GTK_BOX(art->content), art->label, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(art->content), art->image, FALSE, FALSE, 0);
    gtk_container_add(GTK_CONTAINER(art->box), art->content);
    gtk_container_add(info->get_root_widget(info->obj), art->box);
    gtk_widget_add_events(art->box, GDK_BUTTON_PRESS_MASK | GDK_SCROLL_MASK | GDK_SMOOTH_SCROLL_MASK |
                                  GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK);
    g_signal_connect(art->box, "button-press-event", G_CALLBACK(clicked), art);
    g_signal_connect(art->box, "scroll-event", G_CALLBACK(scrolled), art);
    g_signal_connect(art->box, "enter-notify-event", G_CALLBACK(crossed), art);
    g_signal_connect(art->box, "leave-notify-event", G_CALLBACK(crossed), art);
    g_signal_connect(art->content, "notify::scale-factor", G_CALLBACK(scale_changed), art);
    gtk_widget_show_all(art->box);
    gtk_widget_hide(art->image);
    char *share = g_build_filename(g_get_home_dir(), ".local", "share", "oldbook", NULL);
    GFile *directory = g_file_new_for_path(share);
    art->monitor = g_file_monitor_directory(directory, G_FILE_MONITOR_WATCH_MOVES, NULL, NULL);
    if (art->monitor) g_signal_connect(art->monitor, "changed", G_CALLBACK(wallpaper_changed), art);
    g_object_unref(directory);
    g_free(share);
    art->help = oldbook_help_init(GTK_WIDGET(info->get_root_widget(info->obj)));
    art->timer = g_timeout_add_seconds(5, refresh_status, art);
    refresh_status(art);
    return art;
}

void wbcffi_deinit(void *instance) {
    Artwork *art = instance;
    art->disposed = TRUE;
    oldbook_help_deinit(art->help);
    g_source_remove(art->timer);
    if (art->monitor_timer) g_source_remove(art->monitor_timer);
    if (art->monitor) {
        g_file_monitor_cancel(art->monitor);
        g_clear_object(&art->monitor);
    }
    if (art->status) g_subprocess_force_exit(art->status);
    release(art);
}

void wbcffi_update(void *instance) { (void)instance; }
void wbcffi_refresh(void *instance, int signal) { (void)signal; refresh_status(instance); }
void wbcffi_doaction(void *instance, const char *name) { (void)instance; (void)name; }
