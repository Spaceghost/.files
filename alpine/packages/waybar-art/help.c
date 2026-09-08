/* SPDX-License-Identifier: MIT */
#include "help.h"
#include <string.h>

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

static const char installed_key[] = "mbp-intel-hover-help-binding";

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
    gtk_style_context_lookup_color(context, "mbp_intel_workspace_active", &active);
    gtk_style_context_lookup_color(context, "mbp_intel_workspace_secondary", &secondary);
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
    g_debug("mbp-intel-help: rendered %s tooltip", names[binding->kind]);
    g_free(markup);
    g_free(escaped);
    g_free(native);
    return TRUE;
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

void *mbp_intel_help_init(GtkWidget *root) {
    Help *help = g_new0(Help, 1);
    help->root = root;
    help->bindings = g_ptr_array_new();
    help->discover_source = g_idle_add(discover, help);
    return help;
}

void mbp_intel_help_deinit(void *instance) {
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
        if (binding->widget) {
            if (binding->query_handler)
                g_signal_handler_disconnect(binding->widget, binding->query_handler);
            if (binding->button_label_handler)
                g_signal_handler_disconnect(binding->widget, binding->button_label_handler);
            if (binding->style_handler)
                g_signal_handler_disconnect(binding->widget, binding->style_handler);
            g_object_set_data(G_OBJECT(binding->widget), installed_key, NULL);
            g_object_weak_unref(G_OBJECT(binding->widget), widget_gone, binding);
        }
        if (binding->original_attributes) pango_attr_list_unref(binding->original_attributes);
        g_free(binding);
    }
    g_ptr_array_free(help->bindings, TRUE);
    g_free(help);
}
