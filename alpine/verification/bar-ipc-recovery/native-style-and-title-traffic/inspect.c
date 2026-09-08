#define _GNU_SOURCE
#include <gtk/gtk.h>
#include <dlfcn.h>
#include <stdio.h>

static unsigned long attr_calls;
static unsigned long beats;
static char clock_text[80];
static GdkRGBA clock_color;

void gtk_label_set_attributes(GtkLabel *label, PangoAttrList *attrs) {
    static void (*real_set)(GtkLabel *, PangoAttrList *);
    if (!real_set) real_set = dlsym(RTLD_NEXT, "gtk_label_set_attributes");
    attr_calls++;
    real_set(label, attrs);
}

static void visit(GtkWidget *widget, gpointer unused) {
    (void)unused;
    gboolean clock = FALSE;
    for (GtkWidget *parent = widget; parent; parent = gtk_widget_get_parent(parent))
        if (g_str_equal(gtk_widget_get_name(parent), "clock")) clock = TRUE;
    if (clock && GTK_IS_LABEL(widget)) {
        g_strlcpy(clock_text, gtk_label_get_text(GTK_LABEL(widget)), sizeof(clock_text));
        GtkStyleContext *context = gtk_widget_get_style_context(widget);
        gtk_style_context_get_color(context, gtk_style_context_get_state(context), &clock_color);
    }
    if (GTK_IS_CONTAINER(widget)) gtk_container_foreach(GTK_CONTAINER(widget), visit, NULL);
}

static gboolean inspect(gpointer unused) {
    (void)unused;
    const char *path = g_getenv("OLDBOOK_PRIVATE_WAYBAR_INSPECTION");
    if (!path) return G_SOURCE_REMOVE;
    GList *windows = gtk_window_list_toplevels();
    for (GList *item = windows; item; item = item->next) visit(item->data, NULL);
    g_list_free(windows);
    char *line = g_strdup_printf("{\"beats\":%lu,\"monotonic_us\":%lld,\"attributes\":%lu,\"clock\":\"%s\",\"color\":[%.3f,%.3f,%.3f]}\n",
        ++beats, (long long)g_get_monotonic_time(), attr_calls, clock_text,
        clock_color.red, clock_color.green, clock_color.blue);
    g_file_set_contents(path, line, -1, NULL);
    g_free(line);
    return G_SOURCE_CONTINUE;
}

__attribute__((constructor)) static void begin(void) {
    if (g_getenv("OLDBOOK_PRIVATE_WAYBAR_INSPECTION")) g_timeout_add(200, inspect, NULL);
}
