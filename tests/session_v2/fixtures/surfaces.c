/* TEST_ONLY : un processus GTK, plusieurs top-levels Wayland adressables.
 * WHY : éviter N processus terminaux pour N ancrages.
 * CONTRACT : stdin privé du harness, commandes create/quit uniquement.
 * INVARIANT : aucune application, configuration ou fenêtre utilisateur ouverte.
 */
#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <stdio.h>
#include <string.h>

static gboolean input(GIOChannel *channel, GIOCondition condition, gpointer data) {
    (void)channel;
    (void)data;
    if (condition & (G_IO_HUP | G_IO_ERR)) { gtk_main_quit(); return FALSE; }
    char buffer[256];
    if (!fgets(buffer, sizeof buffer, stdin)) { gtk_main_quit(); return FALSE; }
    if (strcmp(buffer, "quit\n") == 0) { gtk_main_quit(); return FALSE; }
    char identity[181];
    if (sscanf(buffer, "create %180s", identity) != 1 ||
        !g_regex_match_simple("^[A-Za-z0-9_.-]{1,180}$", identity, 0, 0)) {
        fprintf(stderr, "Commande TEST_ONLY invalide\n"); return TRUE;
    }
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "TEST_ONLY");
    gtk_window_set_default_size(GTK_WINDOW(window), 120, 80);
    gtk_widget_set_size_request(window, 1, 1);
    gtk_widget_realize(window);
    gtk_widget_show_all(window);
    /* GTK publie son app_id lors du mapping ; l'identité de test suit ce mapping. */
    gdk_wayland_window_set_application_id(gtk_widget_get_window(window), identity);
    gdk_display_flush(gtk_widget_get_display(window));
    printf("created %s\n", identity); fflush(stdout);
    return TRUE;
}

int main(int argc, char **argv) {
    g_set_prgname("TEST_ONLY_SURFACES");
    gtk_init(&argc, &argv);
    setvbuf(stdin, NULL, _IONBF, 0);
    GIOChannel *channel = g_io_channel_unix_new(0);
    g_io_add_watch(channel, G_IO_IN | G_IO_HUP | G_IO_ERR, input, NULL);
    gtk_main();
    g_io_channel_unref(channel);
    return 0;
}
