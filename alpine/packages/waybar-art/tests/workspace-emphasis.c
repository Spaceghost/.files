/* SPDX-License-Identifier: MIT */
/* Compile with help.c and gtk+-3.0, then run with a private DISPLAY. */
#include "../help.h"
#include <string.h>

static guint checks;

static void settle(void) {
    for (guint i = 0; i < 60; ++i) {
        while (g_main_context_iteration(NULL, FALSE)) {}
        g_usleep(2000);
    }
}

static PangoAttribute *attribute_at(GtkLabel *label, PangoAttrType type, guint index) {
    PangoAttrList *attributes = gtk_label_get_attributes(label);
    g_assert_nonnull(attributes);
    PangoAttrIterator *iterator = pango_attr_list_get_iterator(attributes);
    PangoAttribute *result = NULL;
    do {
        gint start, end;
        pango_attr_iterator_range(iterator, &start, &end);
        if (index >= (guint)start && index < (guint)end) {
            PangoAttribute *attribute = pango_attr_iterator_get(iterator, type);
            if (attribute) result = pango_attribute_copy(attribute);
            break;
        }
    } while (pango_attr_iterator_next(iterator));
    pango_attr_iterator_destroy(iterator);
    g_assert_nonnull(result);
    return result;
}

static void expect_weight(GtkLabel *label, guint index, PangoWeight expected) {
    PangoAttribute *attribute = attribute_at(label, PANGO_ATTR_WEIGHT, index);
    g_assert_cmpint(((PangoAttrInt *)attribute)->value, ==, (int)expected);
    pango_attribute_destroy(attribute);
    checks++;
}

static void expect_color(GtkLabel *label, guint index, const char *expected) {
    PangoColor color;
    g_assert_true(pango_color_parse(&color, expected));
    PangoAttribute *attribute = attribute_at(label, PANGO_ATTR_FOREGROUND, index);
    PangoColor actual = ((PangoAttrColor *)attribute)->color;
    g_assert_cmpuint(actual.red, ==, color.red);
    g_assert_cmpuint(actual.green, ==, color.green);
    g_assert_cmpuint(actual.blue, ==, color.blue);
    pango_attribute_destroy(attribute);
    checks++;
}

static GtkWidget *add_workspace(GtkWidget *workspaces, const char *text) {
    GtkWidget *button = gtk_button_new_with_label(text);
    /* Waybar uses pack_start(), which does not emit GtkContainer::add. */
    gtk_box_pack_start(GTK_BOX(workspaces), button, FALSE, FALSE, 0);
    gtk_widget_show_all(button);
    return button;
}

int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    GtkCssProvider *css = gtk_css_provider_new();
    GError *error = NULL;
    g_assert_true(gtk_css_provider_load_from_data(css,
        "@define-color oldbook_workspace_active #ffeeaa;"
        "@define-color oldbook_workspace_secondary #887766;"
        "#workspaces button { color: #aaaaaa; font-weight: 400; background: #101010; }"
        "#workspaces button.focused { color: #ffeeaa; background: #303030; }", -1, &error));
    g_assert_no_error(error);
    gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),
        GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_USER);
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    GtkWidget *workspaces = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_name(workspaces, "workspaces");
    gtk_container_add(GTK_CONTAINER(window), workspaces);
    GtkWidget *first = add_workspace(workspaces, "1: GHOST · ✦ Codex");
    GtkWidget *second = add_workspace(workspaces, "2: ORBIT · Firefox");
    GtkLabel *first_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(first)));
    GtkLabel *second_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(second)));
    PangoAttrList *original = pango_attr_list_new();
    pango_attr_list_insert(original, pango_attr_style_new(PANGO_STYLE_ITALIC));
    gtk_label_set_attributes(first_label, original);
    gtk_style_context_add_class(gtk_widget_get_style_context(first), "focused");
    gtk_widget_show_all(window);
    void *help = oldbook_help_init(window);
    settle();
    expect_weight(first_label, 0, PANGO_WEIGHT_BOLD);
    expect_weight(first_label, 3, PANGO_WEIGHT_BOLD);
    expect_weight(first_label, 14, PANGO_WEIGHT_NORMAL);
    expect_color(first_label, 0, "#ffeeaa");
    expect_color(first_label, 3, "#ffeeaa");
    expect_color(first_label, 14, "#887766");
    expect_weight(second_label, 0, PANGO_WEIGHT_BOLD);
    expect_weight(second_label, 3, PANGO_WEIGHT_NORMAL);
    expect_weight(second_label, 14, PANGO_WEIGHT_NORMAL);
    expect_color(second_label, 3, "#aaaaaa");
    expect_color(second_label, 14, "#887766");

    gtk_style_context_remove_class(gtk_widget_get_style_context(first), "focused");
    gtk_style_context_add_class(gtk_widget_get_style_context(second), "focused");
    settle();
    expect_weight(first_label, 3, PANGO_WEIGHT_NORMAL);
    expect_weight(second_label, 3, PANGO_WEIGHT_BOLD);
    expect_color(second_label, 3, "#ffeeaa");
    expect_color(first_label, 14, "#887766");

    const char *renamed = "12: Écriture · ✦ Codex & <notes>";
    gtk_button_set_label(GTK_BUTTON(second), renamed);
    settle();
    second_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(second)));
    g_assert_cmpstr(gtk_label_get_text(second_label), ==, renamed);
    g_assert_false(gtk_label_get_use_markup(second_label));
    checks += 2;
    guint separator = (guint)(strstr(renamed, " · ") - renamed);
    expect_weight(second_label, 1, PANGO_WEIGHT_BOLD);
    expect_weight(second_label, separator - 1, PANGO_WEIGHT_BOLD);
    expect_weight(second_label, separator, PANGO_WEIGHT_NORMAL);
    expect_weight(second_label, separator + 4, PANGO_WEIGHT_NORMAL);
    expect_color(second_label, separator - 1, "#ffeeaa");
    expect_color(second_label, separator + 4, "#887766");

    /* A Sway rename makes Waybar retire the old button and pack a new one,
     * even when its resulting width is unchanged. */
    gtk_widget_destroy(second);
    second = add_workspace(workspaces, renamed);
    second_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(second)));
    gtk_style_context_add_class(gtk_widget_get_style_context(second), "focused");
    settle();
    expect_weight(second_label, separator - 1, PANGO_WEIGHT_BOLD);
    expect_weight(second_label, separator + 4, PANGO_WEIGHT_NORMAL);
    expect_color(second_label, separator - 1, "#ffeeaa");
    expect_color(second_label, separator + 4, "#887766");

    GtkWidget *third = add_workspace(workspaces, "10: STRATA");
    GtkLabel *third_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(third)));
    gtk_style_context_add_class(gtk_widget_get_style_context(third), "focused");
    settle();
    expect_weight(third_label, 0, PANGO_WEIGHT_BOLD);
    expect_weight(third_label, 1, PANGO_WEIGHT_BOLD);
    expect_weight(third_label, 4, PANGO_WEIGHT_BOLD);
    expect_color(third_label, 0, "#ffeeaa");
    expect_color(third_label, 4, "#ffeeaa");
    gtk_style_context_remove_class(gtk_widget_get_style_context(third), "focused");
    settle();
    expect_weight(third_label, 0, PANGO_WEIGHT_BOLD);
    expect_weight(third_label, 1, PANGO_WEIGHT_BOLD);
    expect_weight(third_label, 4, PANGO_WEIGHT_NORMAL);
    expect_color(third_label, 0, "#aaaaaa");
    expect_color(third_label, 4, "#aaaaaa");
    gtk_style_context_add_class(gtk_widget_get_style_context(third), "focused");
    gtk_button_set_label(GTK_BUTTON(third), "0: STRATA");
    settle();
    third_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(third)));
    expect_weight(third_label, 3, PANGO_WEIGHT_BOLD);
    expect_color(third_label, 3, "#ffeeaa");
    const char *titlecase[] = {
        "0: Strata", "1: Ghost", "2: Orbit", "3: Lab", "4: Signal", "5: Lounge", "10: Strata",
    };
    for (guint i = 0; i < G_N_ELEMENTS(titlecase); ++i) {
        gtk_button_set_label(GTK_BUTTON(third), titlecase[i]);
        gtk_style_context_add_class(gtk_widget_get_style_context(third), "focused");
        settle();
        third_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(third)));
        guint digits = (guint)strspn(titlecase[i], "0123456789");
        guint name_index = digits + 2;
        g_assert_cmpstr(gtk_label_get_text(third_label), ==, titlecase[i]);
        checks++;
        expect_weight(third_label, 0, PANGO_WEIGHT_BOLD);
        expect_weight(third_label, digits - 1, PANGO_WEIGHT_BOLD);
        expect_weight(third_label, name_index, PANGO_WEIGHT_BOLD);
        expect_color(third_label, 0, "#ffeeaa");
        expect_color(third_label, name_index, "#ffeeaa");
        gtk_style_context_remove_class(gtk_widget_get_style_context(third), "focused");
        settle();
        expect_weight(third_label, 0, PANGO_WEIGHT_BOLD);
        expect_weight(third_label, digits - 1, PANGO_WEIGHT_BOLD);
        expect_weight(third_label, name_index, PANGO_WEIGHT_NORMAL);
        expect_color(third_label, 0, "#aaaaaa");
        expect_color(third_label, name_index, "#aaaaaa");
    }
    gtk_style_context_add_class(gtk_widget_get_style_context(third), "focused");
    gtk_button_set_label(GTK_BUTTON(third), "7: Foot");
    settle();
    third_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(third)));
    expect_weight(third_label, 0, PANGO_WEIGHT_BOLD);
    expect_weight(third_label, 3, PANGO_WEIGHT_NORMAL);
    expect_color(third_label, 3, "#887766");
    gtk_button_set_label(GTK_BUTTON(third), "Notes sans numéro · Editor");
    settle();
    third_label = GTK_LABEL(gtk_bin_get_child(GTK_BIN(third)));
    expect_weight(third_label, 0, PANGO_WEIGHT_BOLD);
    expect_weight(third_label, 23, PANGO_WEIGHT_NORMAL);

    /* Keep the label alive after its button is removed, then exercise its
     * signal before deinit: no callback may dereference the dead button. */
    g_object_ref(third_label);
    gtk_widget_destroy(third);
    gtk_label_set_text(third_label, "after workspace removal");
    settle();
    g_object_unref(third_label);
    oldbook_help_deinit(help);
    g_assert_true(pango_attr_list_equal(gtk_label_get_attributes(first_label), original));
    g_assert_null(gtk_label_get_attributes(second_label));
    checks += 2;
    gtk_button_set_label(GTK_BUTTON(second), "safe after deinit");
    gtk_style_context_remove_class(gtk_widget_get_style_context(second), "focused");
    settle();
    gtk_widget_destroy(window);
    settle();
    pango_attr_list_unref(original);

    /* Cancel deferred discovery, and separately destroy all widgets before
     * cleanup, covering both ownership orders used by Waybar on shutdown. */
    window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    help = oldbook_help_init(window);
    oldbook_help_deinit(help);
    gtk_widget_destroy(window);
    settle();
    window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    workspaces = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_set_name(workspaces, "workspaces");
    gtk_container_add(GTK_CONTAINER(window), workspaces);
    add_workspace(workspaces, "1: GHOST");
    help = oldbook_help_init(window);
    settle();
    gtk_widget_destroy(window);
    settle();
    oldbook_help_deinit(help);
    settle();
    checks += 3;
    g_object_unref(css);
    g_print("workspace emphasis: %u checks passed\n", checks);
    return 0;
}
