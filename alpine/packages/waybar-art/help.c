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
    gulong query_handler;
    HelpKind kind;
} Binding;

struct Help {
    GtkWidget *root;
    GtkWidget *workspaces;
    gulong workspace_add_handler;
    guint discover_source;
    guint discover_attempts;
    GPtrArray *bindings;
    gboolean disposed;
};

static const char installed_key[] = "oldbook-hover-help-binding";

static void widget_gone(gpointer data, GObject *where_widget_was) {
    (void)where_widget_was;
    Binding *binding = data;
    binding->widget = NULL;
}

static void workspaces_gone(gpointer data, GObject *where_widget_was) {
    (void)where_widget_was;
    Help *help = data;
    help->workspaces = NULL;
    help->workspace_add_handler = 0;
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

static void watch_workspaces(Help *help, GtkWidget *widget) {
    if (help->workspaces || !GTK_IS_CONTAINER(widget)) return;
    help->workspaces = widget;
    g_object_weak_ref(G_OBJECT(widget), workspaces_gone, help);
    GList *children = gtk_container_get_children(GTK_CONTAINER(widget));
    for (GList *item = children; item; item = item->next) {
        if (GTK_IS_BUTTON(item->data)) attach(help, GTK_WIDGET(item->data), HELP_WORKSPACE);
    }
    g_list_free(children);
    help->workspace_add_handler = g_signal_connect(widget, "add",
                                                    G_CALLBACK(workspace_child_added), help);
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
        g_object_weak_unref(G_OBJECT(help->workspaces), workspaces_gone, help);
    }
    for (guint i = 0; i < help->bindings->len; ++i) {
        Binding *binding = g_ptr_array_index(help->bindings, i);
        binding->owner = NULL;
        if (binding->widget) {
            if (binding->query_handler)
                g_signal_handler_disconnect(binding->widget, binding->query_handler);
            g_object_set_data(G_OBJECT(binding->widget), installed_key, NULL);
            g_object_weak_unref(G_OBJECT(binding->widget), widget_gone, binding);
        }
        g_free(binding);
    }
    g_ptr_array_free(help->bindings, TRUE);
    g_free(help);
}
