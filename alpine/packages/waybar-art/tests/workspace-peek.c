/* SPDX-License-Identifier: MIT */
/* The workspace peek, without a compositor.
 *
 * Compile with help.c and gtk+-3.0 and run under a private DISPLAY. The
 * stills helper is replaced by a script in the fixture's own HOME, so the
 * peek is exercised with known windows and known images and never asks the
 * real compositor to capture anything.
 */
#include "../help.h"
#include <glib/gstdio.h>
#include <stdlib.h>
#include <string.h>

static guint checks;

static void settle(guint rounds) {
    for (guint i = 0; i < rounds; ++i) {
        while (g_main_context_iteration(NULL, FALSE)) {}
        g_usleep(3000);
    }
}

static GtkWidget *add_workspace(GtkWidget *workspaces, const char *text) {
    GtkWidget *button = gtk_button_new_with_label(text);
    gtk_widget_set_name(button, "workspace-button");
    gtk_box_pack_start(GTK_BOX(workspaces), button, FALSE, FALSE, 0);
    gtk_widget_show_all(button);
    return button;
}

static void cross(GtkWidget *widget, GdkEventType type, GdkNotifyType detail) {
    GdkEvent *event = gdk_event_new(type);
    event->crossing.window = g_object_ref(gtk_widget_get_window(widget));
    event->crossing.send_event = TRUE;
    event->crossing.subwindow = NULL;
    event->crossing.time = GDK_CURRENT_TIME;
    event->crossing.mode = GDK_CROSSING_NORMAL;
    event->crossing.detail = detail;
    event->crossing.focus = TRUE;
    gtk_widget_event(widget, event);
    gdk_event_free(event);
}

static GtkWidget *peek_of(GtkWidget *button) {
    return g_object_get_data(G_OBJECT(button), "oldbook-workspace-peek");
}

static guint count_children(GtkWidget *container) {
    GList *children = gtk_container_get_children(GTK_CONTAINER(container));
    guint count = g_list_length(children);
    g_list_free(children);
    return count;
}

/* Wait for the helper to answer, but never hang a failing build. */
static GtkWidget *wait_for_peek(GtkWidget *button, guint deciseconds) {
    for (guint i = 0; i < deciseconds; ++i) {
        settle(40);
        if (peek_of(button)) return peek_of(button);
    }
    return NULL;
}

static void write_helper(const char *home, const char *body) {
    char *bin = g_build_filename(home, ".local", "bin", NULL);
    g_mkdir_with_parents(bin, 0700);
    char *path = g_build_filename(bin, "oldbook-window-stills", NULL);
    GError *error = NULL;
    g_assert_true(g_file_set_contents(path, body, -1, &error));
    g_assert_no_error(error);
    g_assert_cmpint(g_chmod(path, 0700), ==, 0);
    g_free(path);
    g_free(bin);
}

int main(int argc, char **argv) {
    /* GLib caches the home directory on its first use, and the module builds
     * the helper's path from it, so the private HOME has to be in place
     * before any other GLib call, gtk_init included. */
    char template[] = "/tmp/oldbook-peek-XXXXXX";
    char *home = mkdtemp(template);
    if (!home || setenv("HOME", home, 1) != 0) {
        g_printerr("workspace peek: no private HOME\n");
        return 1;
    }
    gtk_init(&argc, &argv);
    g_assert_cmpstr(g_get_home_dir(), ==, home);

    /* One real PNG so the card takes the image path, not the fallback tile. */
    char *image = g_build_filename(home, "still.png", NULL);
    GdkPixbuf *sample = gdk_pixbuf_new(GDK_COLORSPACE_RGB, FALSE, 8, 120, 90);
    gdk_pixbuf_fill(sample, 0x504945ff);
    g_assert_true(gdk_pixbuf_save(sample, image, "png", NULL, NULL));
    g_object_unref(sample);

    char *good = g_strdup_printf(
        "#!/bin/sh\n"
        "printf '{\"workspace\": 2, \"height\": 96, \"windows\": ["
        "{\"id\": 1, \"title\": \"Ghost Planet Terminal With A Very Long Title\","
        " \"still\": \"%s\"},"
        "{\"id\": 2, \"title\": \"Zorak\", \"still\": \"%s\"},"
        "{\"id\": 3, \"title\": \"No capture\"}"
        "]}\\n'\n", image, image);
    write_helper(home, good);
    g_free(good);

    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    GtkWidget *workspaces = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_name(workspaces, "workspaces");
    gtk_container_add(GTK_CONTAINER(window), workspaces);
    GtkWidget *first = add_workspace(workspaces, "1: Ghost");
    GtkWidget *second = add_workspace(workspaces, "2: Orbit");
    gtk_widget_show_all(window);
    void *help = oldbook_help_init(window);
    settle(60);

    /* Sweeping past a workspace must not ask for anything: leave before the
     * dwell elapses and no peek may open, then or later. */
    cross(second, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
    settle(20);
    cross(second, GDK_LEAVE_NOTIFY, GDK_NOTIFY_ANCESTOR);
    settle(200);
    g_assert_null(peek_of(second));
    checks++;

    /* Resting opens the peek with one card per window, captured or not. */
    cross(second, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
    GtkWidget *popover = wait_for_peek(second, 60);
    g_assert_nonnull(popover);
    g_assert_true(GTK_IS_POPOVER(popover));
    g_assert_true(gtk_popover_get_relative_to(GTK_POPOVER(popover)) == second);
    g_assert_cmpstr(gtk_widget_get_name(popover), ==, "oldbook-peek");
    checks += 4;
    GtkWidget *row = gtk_bin_get_child(GTK_BIN(popover));
    g_assert_nonnull(row);
    g_assert_cmpuint(count_children(row), ==, 3);
    checks++;

    /* Each card is a still above a title, and long titles are shortened. */
    GList *cards = gtk_container_get_children(GTK_CONTAINER(row));
    GtkWidget *card = GTK_WIDGET(cards->data);
    g_assert_cmpuint(count_children(card), ==, 2);
    GList *parts = gtk_container_get_children(GTK_CONTAINER(card));
    g_assert_true(GTK_IS_IMAGE(parts->data));
    GtkWidget *caption = GTK_WIDGET(parts->next->data);
    g_assert_true(GTK_IS_LABEL(caption));
    const char *shown = gtk_label_get_text(GTK_LABEL(caption));
    g_assert_cmpuint((guint)g_utf8_strlen(shown, -1), <=, 18);
    g_assert_true(g_str_has_suffix(shown, "…"));
    g_list_free(parts);
    /* The window with no capture still gets a card, with a plain tile. */
    GtkWidget *last = GTK_WIDGET(cards->next->next->data);
    parts = gtk_container_get_children(GTK_CONTAINER(last));
    g_assert_true(GTK_IS_DRAWING_AREA(parts->data));
    g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(parts->next->data)), ==, "No capture");
    g_list_free(parts);
    g_list_free(cards);
    checks += 7;

    /* Optionally save what GTK actually drew, for the package's evidence. */
    if (argc > 1) {
        GtkRequisition natural;
        gtk_widget_get_preferred_size(row, NULL, &natural);
        GtkAllocation allocation = {0, 0, natural.width, natural.height};
        gtk_widget_size_allocate(row, &allocation);
        settle(20);
        cairo_surface_t *shot = cairo_image_surface_create(
            CAIRO_FORMAT_ARGB32, allocation.width + 20, allocation.height + 20);
        cairo_t *cr = cairo_create(shot);
        cairo_set_source_rgba(cr, 0.114, 0.125, 0.129, 0.98);
        cairo_paint(cr);
        cairo_translate(cr, 10, 10);
        gtk_widget_draw(row, cr);
        cairo_destroy(cr);
        g_assert_cmpint(cairo_surface_write_to_png(shot, argv[1]), ==, CAIRO_STATUS_SUCCESS);
        cairo_surface_destroy(shot);
        checks++;
    }

    /* Leaving closes it and forgets it. */
    cross(second, GDK_LEAVE_NOTIFY, GDK_NOTIFY_ANCESTOR);
    settle(60);
    g_assert_null(peek_of(second));
    checks++;

    /* Crossing into the button's own label is not leaving the button. */
    cross(second, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
    g_assert_nonnull(wait_for_peek(second, 60));
    cross(second, GDK_LEAVE_NOTIFY, GDK_NOTIFY_INFERIOR);
    settle(40);
    g_assert_nonnull(peek_of(second));
    cross(second, GDK_LEAVE_NOTIFY, GDK_NOTIFY_ANCESTOR);
    settle(60);
    g_assert_null(peek_of(second));
    checks += 2;

    /* A workspace whose label carries no number asks for nothing. */
    gtk_button_set_label(GTK_BUTTON(first), "scratch");
    settle(20);
    cross(first, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
    settle(200);
    g_assert_null(peek_of(first));
    cross(first, GDK_LEAVE_NOTIFY, GDK_NOTIFY_ANCESTOR);
    checks++;

    /* A helper that fails, prints nothing, or prints nonsense opens nothing. */
    const char *bad[] = {"#!/bin/sh\nexit 1\n", "#!/bin/sh\nprintf ''\n",
                         "#!/bin/sh\nprintf 'not json'\n",
                         "#!/bin/sh\nprintf '{\"windows\": []}\\n'\n"};
    for (guint i = 0; i < G_N_ELEMENTS(bad); ++i) {
        write_helper(home, bad[i]);
        cross(second, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
        settle(300);
        g_assert_null(peek_of(second));
        cross(second, GDK_LEAVE_NOTIFY, GDK_NOTIFY_ANCESTOR);
        settle(20);
        checks++;
    }

    /* Shutting down with a peek open must not leave a popover behind. */
    write_helper(home, "#!/bin/sh\nprintf '{\"windows\": [{\"id\": 1, \"title\": \"One\"}]}\\n'\n");
    cross(second, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
    g_assert_nonnull(wait_for_peek(second, 60));
    oldbook_help_deinit(help);
    settle(60);
    g_assert_null(peek_of(second));
    checks++;
    gtk_widget_destroy(window);
    settle(40);

    /* And a peek that is still opening when the bar goes away is harmless. */
    window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    workspaces = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_name(workspaces, "workspaces");
    gtk_container_add(GTK_CONTAINER(window), workspaces);
    GtkWidget *only = add_workspace(workspaces, "3: Lab");
    gtk_widget_show_all(window);
    help = oldbook_help_init(window);
    settle(60);
    cross(only, GDK_ENTER_NOTIFY, GDK_NOTIFY_ANCESTOR);
    settle(20);
    oldbook_help_deinit(help);
    gtk_widget_destroy(window);
    settle(80);
    checks++;

    g_free(image);
    g_print("workspace peek: %u checks passed\n", checks);
    return 0;
}
