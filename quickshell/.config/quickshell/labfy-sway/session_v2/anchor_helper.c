/* WHY : une seule application possédée fournit les feuilles temporaires.
 * CONTRACT : stdin privé, create <identité> / quit, 256 fenêtres maximum.
 * INVARIANT : aucun lancement applicatif ni accès aux fenêtres d'autrui.
 */
#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <stdio.h>
#include <string.h>

static unsigned created;
static gboolean input(GIOChannel *channel, GIOCondition condition, gpointer data) {
    (void)channel; (void)data;
    if (condition & (G_IO_HUP | G_IO_ERR)) { gtk_main_quit(); return FALSE; }
    char buffer[256];
    if (!fgets(buffer, sizeof buffer, stdin)) { gtk_main_quit(); return FALSE; }
    if (!strcmp(buffer, "quit\n")) { gtk_main_quit(); return FALSE; }
    if (created >= 256 || !g_regex_match_simple(
        "^create labfy-v2-anchor-[a-f0-9]{32}-[A-Za-z0-9_.-]{1,96}\\n$", buffer, 0, 0)) {
        gtk_main_quit(); return FALSE;
    }
    buffer[strcspn(buffer, "\n")] = 0;
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "Restauration de session…");
    gtk_window_set_default_size(GTK_WINDOW(window), 120, 80);
    gtk_widget_set_size_request(window, 1, 1);
    gtk_widget_show_all(window);
    /* GTK remplace app_id au mapping : publier notre identité ensuite. */
    gdk_wayland_window_set_application_id(gtk_widget_get_window(window), buffer + 7);
    gdk_display_flush(gtk_widget_get_display(window));
    ++created;
    return TRUE;
}

int main(int argc, char **argv) {
    g_set_prgname("labfy-v2-anchor");
    gtk_init(&argc, &argv);
    if (!GDK_IS_WAYLAND_DISPLAY(gdk_display_get_default())) return 2;
    setvbuf(stdin, NULL, _IONBF, 0);
    GIOChannel *channel = g_io_channel_unix_new(0);
    g_io_add_watch(channel, G_IO_IN | G_IO_HUP | G_IO_ERR, input, NULL);
    gtk_main();
    g_io_channel_unref(channel);
    return 0;
}
