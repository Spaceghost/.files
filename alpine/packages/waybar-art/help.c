/* SPDX-License-Identifier: MIT */
#include "help.h"
#include <json-glib/json-glib.h>
#include <stdlib.h>
#include <string.h>

/* Rest the pointer on a workspace for this long and its windows appear. Short
 * enough to feel like part of the hover, long enough that sweeping the bar
 * never asks the compositor for a single capture. */
#define PEEK_DWELL_MS 350
#define PEEK_HEIGHT 96
#define PEEK_MAX 6
#define PEEK_TITLE_WIDTH 18

typedef enum {
    HELP_WORKSPACE,
    HELP_WINDOW,
    HELP_MODE,
    HELP_CPU,
} HelpKind;

typedef struct Help Help;

typedef struct {
    Help *owner;
    GtkWidget *widget;
    GtkWidget *label;
    gulong query_handler;
    gulong button_label_handler;
    gulong label_handler;
    gulong style_handler;
    PangoAttrList *original_attributes;
    gboolean styling;
    HelpKind kind;
    /* Workspace peek: a dwell timer, the running stills helper and the
     * popover it fills. Only one workspace peeks at a time. */
    gulong enter_handler;
    gulong leave_handler;
    guint dwell_source;
    GSubprocess *stills;
    GtkWidget *popover;
    gboolean hovered;
} Binding;

struct Help {
    GtkWidget *root;
    GtkWidget *workspaces;
    gulong workspace_add_handler;
    gulong workspace_allocate_handler;
    guint discover_source;
    guint discover_attempts;
    GPtrArray *bindings;
    gboolean disposed;
};

static const char installed_key[] = "oldbook-hover-help-binding";
/* The open peek is published on its button so a test fixture can find it
 * without reaching into this file's private binding record. */
static const char peek_key[] = "oldbook-workspace-peek";

static void widget_gone(gpointer data, GObject *where_widget_was) {
    (void)where_widget_was;
    Binding *binding = data;
    binding->widget = NULL;
}

static void label_gone(gpointer data, GObject *where_widget_was) {
    (void)where_widget_was;
    Binding *binding = data;
    binding->label = NULL;
    g_clear_pointer(&binding->original_attributes, pango_attr_list_unref);
}

static void attribute_range(PangoAttrList *attributes, PangoAttribute *attribute,
                            guint start, guint end) {
    attribute->start_index = start;
    attribute->end_index = end;
    pango_attr_list_change(attributes, attribute);
}

static void foreground_range(PangoAttrList *attributes, const GdkRGBA *color,
                             guint start, guint end) {
    attribute_range(attributes, pango_attr_foreground_new(
        (guint16)(CLAMP(color->red, 0., 1.) * 65535. + .5),
        (guint16)(CLAMP(color->green, 0., 1.) * 65535. + .5),
        (guint16)(CLAMP(color->blue, 0., 1.) * 65535. + .5)), start, end);
    attribute_range(attributes, pango_attr_foreground_alpha_new(
        (guint16)(CLAMP(color->alpha, 0., 1.) * 65535. + .5)), start, end);
}

static guint workspace_base_end(const char *text, guint number_end) {
    const char *separator = strstr(text, " · ");
    if (separator) return (guint)(separator - text);
    /* These are the service's named empty workspaces. A bare "7: Foot"
     * otherwise cannot distinguish a generated process from a custom name;
     * keep that ambiguous suffix subdued instead of emphasizing a process. */
    static const char *named[] = {
        "0: STRATA", "1: GHOST", "2: ORBIT", "3: LAB", "4: SIGNAL", "5: LOUNGE", "10: STRATA",
    };
    for (guint i = 0; i < G_N_ELEMENTS(named); ++i)
        if (g_ascii_strcasecmp(text, named[i]) == 0) return (guint)strlen(text);
    if (number_end && text[number_end] == ':') return number_end;
    return (guint)strlen(text);
}

static void emphasize_workspace(Binding *binding) {
    if (!binding->owner || binding->owner->disposed || !binding->widget ||
            !binding->label || binding->styling) return;
    binding->styling = TRUE;
    GtkLabel *label = GTK_LABEL(binding->label);
    const char *text = gtk_label_get_text(label);
    guint number_end = (guint)strspn(text, "0123456789");
    guint base_end = workspace_base_end(text, number_end);
    GtkStyleContext *context = gtk_widget_get_style_context(binding->widget);
    gboolean focused = gtk_style_context_has_class(context, "focused");
    GdkRGBA normal;
    gtk_style_context_get_color(context, gtk_style_context_get_state(context), &normal);
    GdkRGBA active = normal, secondary = normal;
    gtk_style_context_lookup_color(context, "oldbook_workspace_active", &active);
    gtk_style_context_lookup_color(context, "oldbook_workspace_secondary", &secondary);
    PangoAttrList *attributes = binding->original_attributes
        ? pango_attr_list_copy(binding->original_attributes) : pango_attr_list_new();
    attribute_range(attributes, pango_attr_weight_new(PANGO_WEIGHT_NORMAL), 0, G_MAXUINT);
    foreground_range(attributes, &normal, 0, G_MAXUINT);
    guint bold_end = focused ? base_end : number_end;
    if (bold_end)
        attribute_range(attributes, pango_attr_weight_new(PANGO_WEIGHT_BOLD), 0, bold_end);
    if (focused && base_end) foreground_range(attributes, &active, 0, base_end);
    if (text[base_end]) foreground_range(attributes, &secondary, base_end, G_MAXUINT);
    PangoAttrList *current = gtk_label_get_attributes(label);
    if (!current || !pango_attr_list_equal(current, attributes))
        gtk_label_set_attributes(label, attributes);
    pango_attr_list_unref(attributes);
    binding->styling = FALSE;
}

static void workspace_label_changed(GObject *object, GParamSpec *property, gpointer data) {
    (void)object;
    (void)property;
    emphasize_workspace(data);
}

static void workspace_style_changed(GtkWidget *widget, gpointer data) {
    (void)widget;
    emphasize_workspace(data);
}

static void watch_workspace_label(Binding *binding) {
    GtkWidget *label = gtk_bin_get_child(GTK_BIN(binding->widget));
    if (label == binding->label) return;
    if (binding->label) {
        g_signal_handler_disconnect(binding->label, binding->label_handler);
        gtk_label_set_attributes(GTK_LABEL(binding->label), binding->original_attributes);
        g_object_weak_unref(G_OBJECT(binding->label), label_gone, binding);
    }
    binding->label = NULL;
    g_clear_pointer(&binding->original_attributes, pango_attr_list_unref);
    if (!GTK_IS_LABEL(label)) return;
    binding->label = label;
    PangoAttrList *attributes = gtk_label_get_attributes(GTK_LABEL(label));
    if (attributes) binding->original_attributes = pango_attr_list_copy(attributes);
    g_object_weak_ref(G_OBJECT(label), label_gone, binding);
    binding->label_handler = g_signal_connect(label, "notify::label",
                                              G_CALLBACK(workspace_label_changed), binding);
    emphasize_workspace(binding);
}

static void workspace_button_label_changed(GObject *object, GParamSpec *property, gpointer data) {
    (void)object;
    (void)property;
    Binding *binding = data;
    if (!binding->owner || binding->owner->disposed || !binding->widget) return;
    watch_workspace_label(binding);
    emphasize_workspace(binding);
}

static void workspaces_gone(gpointer data, GObject *where_widget_was) {
    (void)where_widget_was;
    Help *help = data;
    help->workspaces = NULL;
    help->workspace_add_handler = 0;
    help->workspace_allocate_handler = 0;
}

static char *native_text(GtkWidget *widget, HelpKind kind) {
    for (GtkWidget *current = widget; current; current = gtk_widget_get_parent(current)) {
        char *text = gtk_widget_get_tooltip_text(current);
        if (text && *text) return text;
        g_free(text);
        if (strcmp(gtk_widget_get_name(current), "window") == 0) break;
    }
    if (kind == HELP_WORKSPACE && GTK_IS_BUTTON(widget)) {
        const char *label = gtk_button_get_label(GTK_BUTTON(widget));
        return g_strdup(label ? label : "Workspace");
    }
    if (GTK_IS_LABEL(widget)) {
        const char *label = gtk_label_get_text(GTK_LABEL(widget));
        if (label && *label) return g_strdup(label);
    }
    return g_strdup(kind == HELP_CPU ? "Per-core activity" : "Active control");
}

static gboolean query_help(GtkWidget *widget, gint x, gint y, gboolean keyboard_mode,
                           GtkTooltip *tooltip, gpointer data) {
    (void)x;
    (void)y;
    (void)keyboard_mode;
    Binding *binding = data;
    if (!binding->owner || binding->owner->disposed) return FALSE;
    char *native = native_text(widget, binding->kind);
    char *escaped = g_markup_escape_text(native, -1);
    char *markup = NULL;
    switch (binding->kind) {
    case HELP_WORKSPACE:
        markup = g_strdup_printf(
            "<b>COAST TO COAST CHANNEL</b>\n%s\n\n"
            "Left: tune to this workspace · Scroll: cruise the channels", escaped);
        break;
    case HELP_WINDOW:
        markup = g_strdup_printf(
            "<b>FOCUSED TRANSMISSION</b>\n%s\n\n"
            "Left: choose an open window\n"
            "Window: Super+Space toggles tile/float", escaped);
        break;
    case HELP_MODE:
        markup = g_strdup_printf(
            "<b>CONTROL MODE</b>\n%s\n\n"
            "Resize controls are live. Return or Escape: back to the broadcast.", escaped);
        break;
    case HELP_CPU:
        markup = g_strdup_printf(
            "<b>GHOST REACTOR</b>\n%s\n\nLeft: open btop", escaped);
        break;
    }
    gtk_tooltip_set_markup(tooltip, markup);
    static const char *names[] = {"workspace", "window", "mode", "cpu"};
    g_debug("oldbook-help: rendered %s tooltip", names[binding->kind]);
    g_free(markup);
    g_free(escaped);
    g_free(native);
    return TRUE;
}

/* ---- Workspace peek ---------------------------------------------------- */

static void close_peek(Binding *binding) {
    if (binding->dwell_source) {
        g_source_remove(binding->dwell_source);
        binding->dwell_source = 0;
    }
    if (binding->stills) {
        g_subprocess_force_exit(binding->stills);
        g_clear_object(&binding->stills);
    }
    if (binding->popover) {
        gtk_popover_popdown(GTK_POPOVER(binding->popover));
        gtk_widget_destroy(binding->popover);
        binding->popover = NULL;
    }
    if (binding->widget) g_object_set_data(G_OBJECT(binding->widget), peek_key, NULL);
}

static int workspace_number(Binding *binding) {
    if (!binding->label) return -1;
    const char *text = gtk_label_get_text(GTK_LABEL(binding->label));
    if (!text || !g_ascii_isdigit(*text)) return -1;
    long value = strtol(text, NULL, 10);
    return value >= 0 && value < 1000 ? (int)value : -1;
}

static char *shorten(const char *text) {
    if (!text || !*text) return g_strdup("Window");
    glong length = g_utf8_strlen(text, -1);
    if (length <= PEEK_TITLE_WIDTH) return g_strdup(text);
    char *cut = g_utf8_substring(text, 0, PEEK_TITLE_WIDTH - 1);
    char *result = g_strconcat(cut, "…", NULL);
    g_free(cut);
    return result;
}

/* One card per window: the still above its own short title. A window whose
 * capture failed keeps its place with a plain tile, so the peek never
 * silently drops a window from the count. */
static GtkWidget *peek_card(JsonObject *window, int scale) {
    GtkWidget *card = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    gtk_style_context_add_class(gtk_widget_get_style_context(card), "oldbook-peek-card");
    JsonNode *node = json_object_get_member(window, "still");
    const char *still = node && JSON_NODE_HOLDS_VALUE(node) &&
                        json_node_get_value_type(node) == G_TYPE_STRING
        ? json_node_get_string(node) : NULL;
    GtkWidget *image = NULL;
    if (still && *still) {
        GdkPixbuf *pixbuf = gdk_pixbuf_new_from_file(still, NULL);
        if (pixbuf) {
            cairo_surface_t *surface = gdk_cairo_surface_create_from_pixbuf(pixbuf, scale, NULL);
            image = gtk_image_new_from_surface(surface);
            cairo_surface_destroy(surface);
            g_object_unref(pixbuf);
        }
    }
    if (!image) {
        image = gtk_drawing_area_new();
        gtk_widget_set_size_request(image, PEEK_HEIGHT * 4 / 3, PEEK_HEIGHT);
    }
    gtk_style_context_add_class(gtk_widget_get_style_context(image), "oldbook-peek-still");
    gtk_box_pack_start(GTK_BOX(card), image, FALSE, FALSE, 0);
    node = json_object_get_member(window, "title");
    const char *title = node && JSON_NODE_HOLDS_VALUE(node) &&
                        json_node_get_value_type(node) == G_TYPE_STRING
        ? json_node_get_string(node) : NULL;
    char *shortened = shorten(title);
    GtkWidget *caption = gtk_label_new(shortened);
    g_free(shortened);
    gtk_label_set_ellipsize(GTK_LABEL(caption), PANGO_ELLIPSIZE_END);
    gtk_label_set_max_width_chars(GTK_LABEL(caption), PEEK_TITLE_WIDTH);
    gtk_widget_set_halign(caption, GTK_ALIGN_CENTER);
    gtk_style_context_add_class(gtk_widget_get_style_context(caption), "oldbook-peek-title");
    gtk_box_pack_start(GTK_BOX(card), caption, FALSE, FALSE, 0);
    return card;
}

static void show_peek(Binding *binding, const char *json) {
    if (!binding->hovered || !binding->widget) return;
    JsonParser *parser = json_parser_new();
    GtkWidget *row = NULL;
    if (json_parser_load_from_data(parser, json, -1, NULL) &&
            JSON_NODE_HOLDS_OBJECT(json_parser_get_root(parser))) {
        JsonObject *root = json_node_get_object(json_parser_get_root(parser));
        JsonNode *node = json_object_get_member(root, "windows");
        JsonArray *windows = node && JSON_NODE_HOLDS_ARRAY(node) ? json_node_get_array(node) : NULL;
        guint count = windows ? json_array_get_length(windows) : 0;
        if (count) {
            int scale = gtk_widget_get_scale_factor(binding->widget);
            row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
            for (guint i = 0; i < count && i < PEEK_MAX; ++i) {
                JsonNode *item = json_array_get_element(windows, i);
                if (!JSON_NODE_HOLDS_OBJECT(item)) continue;
                gtk_box_pack_start(GTK_BOX(row), peek_card(json_node_get_object(item), scale > 0 ? scale : 1),
                                   FALSE, FALSE, 0);
            }
        }
    }
    g_object_unref(parser);
    if (!row) return;
    binding->popover = gtk_popover_new(binding->widget);
    gtk_widget_set_name(binding->popover, "oldbook-peek");
    gtk_popover_set_position(GTK_POPOVER(binding->popover), GTK_POS_BOTTOM);
    gtk_popover_set_modal(GTK_POPOVER(binding->popover), FALSE);
    gtk_container_set_border_width(GTK_CONTAINER(binding->popover), 10);
    gtk_container_add(GTK_CONTAINER(binding->popover), row);
    gtk_widget_show_all(row);
    gtk_popover_popup(GTK_POPOVER(binding->popover));
    g_object_set_data(G_OBJECT(binding->widget), peek_key, binding->popover);
}

static void stills_ready(GObject *source, GAsyncResult *result, gpointer data) {
    Binding *binding = data;
    char *output = NULL;
    gboolean ok = g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source), result,
                                                       &output, NULL, NULL);
    if (binding->owner && !binding->owner->disposed && binding->stills == G_SUBPROCESS(source)) {
        g_clear_object(&binding->stills);
        if (ok && output && *output) show_peek(binding, output);
    }
    g_free(output);
}

static gboolean peek_now(gpointer data) {
    Binding *binding = data;
    binding->dwell_source = 0;
    if (!binding->owner || binding->owner->disposed || !binding->hovered) return G_SOURCE_REMOVE;
    int workspace = workspace_number(binding);
    if (workspace < 0) return G_SOURCE_REMOVE;
    char number[16];
    char height[16];
    g_snprintf(number, sizeof number, "%d", workspace);
    g_snprintf(height, sizeof height, "%d", PEEK_HEIGHT);
    char *helper = g_build_filename(g_get_home_dir(), ".local", "bin",
                                    "oldbook-window-stills", NULL);
    binding->stills = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                                       G_SUBPROCESS_FLAGS_STDERR_SILENCE, NULL,
                                       helper, "--workspace", number, "--height", height, NULL);
    g_free(helper);
    if (binding->stills)
        g_subprocess_communicate_utf8_async(binding->stills, NULL, NULL, stills_ready, binding);
    return G_SOURCE_REMOVE;
}

static gboolean workspace_crossed(GtkWidget *widget, GdkEventCrossing *event, gpointer data) {
    (void)widget;
    Binding *binding = data;
    if (!binding->owner || binding->owner->disposed) return FALSE;
    if (event->type == GDK_ENTER_NOTIFY) {
        if (binding->hovered) return FALSE;
        binding->hovered = TRUE;
        close_peek(binding);
        binding->dwell_source = g_timeout_add(PEEK_DWELL_MS, peek_now, binding);
    } else if (event->detail != GDK_NOTIFY_INFERIOR) {
        binding->hovered = FALSE;
        close_peek(binding);
    }
    return FALSE;
}

static void attach(Help *help, GtkWidget *widget, HelpKind kind) {
    if (g_object_get_data(G_OBJECT(widget), installed_key)) return;
    Binding *binding = g_new0(Binding, 1);
    binding->owner = help;
    binding->widget = widget;
    binding->kind = kind;
    binding->query_handler = g_signal_connect(widget, "query-tooltip",
                                               G_CALLBACK(query_help), binding);
    gtk_widget_set_has_tooltip(widget, TRUE);
    g_object_set_data(G_OBJECT(widget), installed_key, binding);
    g_object_weak_ref(G_OBJECT(widget), widget_gone, binding);
    g_ptr_array_add(help->bindings, binding);
    if (kind == HELP_WORKSPACE && GTK_IS_BUTTON(widget)) {
        binding->button_label_handler = g_signal_connect(widget, "notify::label",
            G_CALLBACK(workspace_button_label_changed), binding);
        binding->style_handler = g_signal_connect(widget, "style-updated",
            G_CALLBACK(workspace_style_changed), binding);
        gtk_widget_add_events(widget, GDK_ENTER_NOTIFY_MASK | GDK_LEAVE_NOTIFY_MASK);
        binding->enter_handler = g_signal_connect(widget, "enter-notify-event",
            G_CALLBACK(workspace_crossed), binding);
        binding->leave_handler = g_signal_connect(widget, "leave-notify-event",
            G_CALLBACK(workspace_crossed), binding);
        watch_workspace_label(binding);
    }
}

static void attach_descendant(GtkWidget *widget, gpointer data) {
    Binding *parent = data;
    attach(parent->owner, widget, parent->kind);
    if (GTK_IS_CONTAINER(widget))
        gtk_container_foreach(GTK_CONTAINER(widget), attach_descendant, parent);
}

static void attach_tree(Help *help, GtkWidget *widget, HelpKind kind) {
    attach(help, widget, kind);
    Binding context = {.owner = help, .kind = kind};
    if (GTK_IS_CONTAINER(widget))
        gtk_container_foreach(GTK_CONTAINER(widget), attach_descendant, &context);
}

static void workspace_child_added(GtkContainer *container, GtkWidget *child, gpointer data) {
    (void)container;
    Help *help = data;
    if (!help->disposed && GTK_IS_BUTTON(child)) attach(help, child, HELP_WORKSPACE);
}

static void discover_workspace_children(Help *help) {
    if (help->disposed || !help->workspaces) return;
    /* Renames retire entire buttons. Release completed weak bindings so a
     * long-running bar does not retain one record for every past app name. */
    for (guint i = 0; i < help->bindings->len;) {
        Binding *binding = g_ptr_array_index(help->bindings, i);
        if (binding->widget || binding->label) {
            i++;
        } else {
            close_peek(binding);
            g_ptr_array_remove_index_fast(help->bindings, i);
            g_free(binding);
        }
    }
    GList *children = gtk_container_get_children(GTK_CONTAINER(help->workspaces));
    for (GList *item = children; item; item = item->next) {
        if (GTK_IS_BUTTON(item->data)) attach(help, GTK_WIDGET(item->data), HELP_WORKSPACE);
    }
    g_list_free(children);
}

static void workspaces_allocated(GtkWidget *widget, GtkAllocation *allocation, gpointer data) {
    (void)widget;
    (void)allocation;
    /* GtkBox::pack_start bypasses GtkContainer::add. Waybar uses it when
     * recreating a renamed workspace button; inspect the resulting layout
     * rather than polling or retaining a callback for every retired button. */
    discover_workspace_children(data);
}

static void watch_workspaces(Help *help, GtkWidget *widget) {
    if (help->workspaces || !GTK_IS_CONTAINER(widget)) return;
    help->workspaces = widget;
    g_object_weak_ref(G_OBJECT(widget), workspaces_gone, help);
    discover_workspace_children(help);
    help->workspace_add_handler = g_signal_connect(widget, "add",
                                                    G_CALLBACK(workspace_child_added), help);
    help->workspace_allocate_handler = g_signal_connect(widget, "size-allocate",
                                                        G_CALLBACK(workspaces_allocated), help);
}

static void discover_widget(GtkWidget *widget, gpointer data) {
    Help *help = data;
    const char *name = gtk_widget_get_name(widget);
    if (strcmp(name, "workspaces") == 0) {
        watch_workspaces(help, widget);
    } else if (strcmp(name, "window") == 0) {
        attach_tree(help, widget, HELP_WINDOW);
    } else if (strcmp(name, "mode") == 0) {
        attach(help, widget, HELP_MODE);
    } else if (strcmp(name, "cpu") == 0) {
        attach(help, widget, HELP_CPU);
    }
    if (GTK_IS_CONTAINER(widget)) {
        gtk_container_foreach(GTK_CONTAINER(widget), discover_widget, help);
    }
}

static gboolean discover(gpointer data) {
    Help *help = data;
    help->discover_source = 0;
    if (help->disposed) return G_SOURCE_REMOVE;
    GtkWidget *toplevel = gtk_widget_get_toplevel(help->root);
    if (GTK_IS_WINDOW(toplevel)) discover_widget(toplevel, help);
    if (help->bindings->len == 0 && ++help->discover_attempts < 20) {
        help->discover_source = g_timeout_add(25, discover, help);
    }
    return G_SOURCE_REMOVE;
}

void *oldbook_help_init(GtkWidget *root) {
    Help *help = g_new0(Help, 1);
    help->root = root;
    help->bindings = g_ptr_array_new();
    help->discover_source = g_idle_add(discover, help);
    return help;
}

void oldbook_help_deinit(void *instance) {
    Help *help = instance;
    help->disposed = TRUE;
    if (help->discover_source) g_source_remove(help->discover_source);
    if (help->workspaces) {
        if (help->workspace_add_handler)
            g_signal_handler_disconnect(help->workspaces, help->workspace_add_handler);
        if (help->workspace_allocate_handler)
            g_signal_handler_disconnect(help->workspaces, help->workspace_allocate_handler);
        g_object_weak_unref(G_OBJECT(help->workspaces), workspaces_gone, help);
    }
    for (guint i = 0; i < help->bindings->len; ++i) {
        Binding *binding = g_ptr_array_index(help->bindings, i);
        binding->owner = NULL;
        if (binding->label) {
            if (binding->label_handler)
                g_signal_handler_disconnect(binding->label, binding->label_handler);
            gtk_label_set_attributes(GTK_LABEL(binding->label), binding->original_attributes);
            g_object_weak_unref(G_OBJECT(binding->label), label_gone, binding);
        }
        binding->hovered = FALSE;
        close_peek(binding);
        if (binding->widget) {
            if (binding->query_handler)
                g_signal_handler_disconnect(binding->widget, binding->query_handler);
            if (binding->button_label_handler)
                g_signal_handler_disconnect(binding->widget, binding->button_label_handler);
            if (binding->style_handler)
                g_signal_handler_disconnect(binding->widget, binding->style_handler);
            if (binding->enter_handler)
                g_signal_handler_disconnect(binding->widget, binding->enter_handler);
            if (binding->leave_handler)
                g_signal_handler_disconnect(binding->widget, binding->leave_handler);
            g_object_set_data(G_OBJECT(binding->widget), installed_key, NULL);
            g_object_weak_unref(G_OBJECT(binding->widget), widget_gone, binding);
        }
        if (binding->original_attributes) pango_attr_list_unref(binding->original_attributes);
        g_free(binding);
    }
    g_ptr_array_free(help->bindings, TRUE);
    g_free(help);
}
