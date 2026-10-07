#!/usr/bin/python3
"""Interface GTK4 Labfy ; la session réelle est créée exclusivement par greetd."""
import argparse
from datetime import datetime
import locale
from pathlib import Path
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from accounts import users
from auth import AuthFlow
from avatar_icon import system_icon
from system_state import battery, backlight, read_last_user, save_last_user, set_brightness

CSS = Path("/usr/local/share/labfy-greeter/labfy-greeter.css")
if not CSS.exists():
    CSS = Path(__file__).resolve().parent.parent / "style/labfy-greeter.css"


class Greeter(Gtk.Application):
    def __init__(self, preview=False):
        super().__init__(application_id="org.labfy.Greeter.Preview" if preview else "org.labfy.Greeter")
        self.preview = preview
        self.flow = None if preview else AuthFlow()
        self.busy = False
        self.current_user = None
        self.pending_kind = None
        self.light = None
        self.start_called = False
        self.selection_ready = False
        self.connect("activate", self.activate)

    def activate(self, *_):
        provider = Gtk.CssProvider()
        provider.load_from_path(str(CSS))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = Gtk.ApplicationWindow(application=self, title="Labfy Greeter")
        self.window.set_default_size(1200, 760)
        if not self.preview:
            self.window.fullscreen()
        canvas = Gtk.Overlay()
        canvas.add_css_class("canvas")
        self.window.set_child(canvas)
        shade = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        shade.add_css_class("shade")
        canvas.set_child(shade)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        layout.set_margin_top(48)
        layout.set_margin_bottom(36)
        layout.set_margin_start(32)
        layout.set_margin_end(32)
        shade.append(layout)

        # INVARIANT: l'horloge et la date sont centrées dans toute la fenêtre ;
        # aucun widget de statut ne participe à leur allocation horizontale.
        clock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        clock.set_halign(Gtk.Align.CENTER)
        layout.append(clock)
        self.time = Gtk.Label()
        self.time.add_css_class("clock")
        clock.append(self.time)
        self.date = Gtk.Label()
        self.date.add_css_class("date")
        clock.append(self.date)
        self.refresh_clock()
        GLib.timeout_add_seconds(15, self.refresh_clock)

        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        middle.set_valign(Gtk.Align.CENTER)
        layout.append(middle)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        card.add_css_class("login-card")
        card.set_halign(Gtk.Align.CENTER)
        card.set_size_request(410, -1)
        middle.append(card)
        self.avatar_picture = Gtk.Picture()
        self.avatar_picture.set_size_request(68, 68)
        self.avatar_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.avatar_picture.add_css_class("avatar-picture")
        self.avatar_picture.set_halign(Gtk.Align.CENTER)
        card.append(self.avatar_picture)
        self.avatar_fallback = Gtk.Label(label="")
        self.avatar_fallback.add_css_class("avatar")
        card.append(self.avatar_fallback)
        title = Gtk.Label(label="Bienvenue")
        title.add_css_class("card-title")
        card.append(title)
        self.selector = Gtk.DropDown.new_from_strings((['Utilisateur de démonstration'] if self.preview else users()) + ['Autre utilisateur…'])
        self.selector.add_css_class("user-selector")
        self.selector.connect("notify::selected", self.user_changed)
        card.append(self.selector)
        self.manual = Gtk.Entry(placeholder_text="Nom utilisateur")
        self.manual.connect("activate", lambda *_: self.submit())
        self.manual.connect("changed", lambda *_: self.refresh_avatar(self.manual.get_text().strip()))
        self.manual.set_visible(False)
        card.append(self.manual)
        self.prompt = Gtk.Label(label="Mot de passe")
        self.prompt.set_xalign(0)
        self.prompt.add_css_class("secondary")
        card.append(self.prompt)
        self.entry = Gtk.Entry()
        self.entry.set_visibility(False)
        self.entry.connect("activate", lambda *_: self.submit())
        card.append(self.entry)
        self.error = Gtk.Label()
        self.error.add_css_class("error")
        self.error.set_wrap(True)
        self.error.set_xalign(0)
        card.append(self.error)
        self.button = Gtk.Button(label="Connexion")
        self.button.add_css_class("primary")
        self.button.connect("clicked", lambda *_: self.submit())
        card.append(self.button)
        if self.preview:
            self.button.set_sensitive(False)
            self.entry.set_sensitive(False)
            self.error.set_text("Aperçu · authentification désactivée")
        else:
            remembered = read_last_user()
            names = users()
            if remembered in names:
                self.selector.set_selected(names.index(remembered))
            self.entry.set_sensitive(False)
        self.refresh_avatar(self.username() if not self.preview else "")

        # CenterBox maintient la luminosité au centre même si l'état batterie
        # change de longueur ou disparaît ; le bloc haut reste indépendant.
        bottom = Gtk.CenterBox()
        layout.append(bottom)
        self.battery_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        self.battery_box.set_valign(Gtk.Align.CENTER)
        bottom.set_start_widget(self.battery_box)
        self.battery_icon = Gtk.Label()
        self.battery_icon.add_css_class("battery-icon")
        self.battery_box.append(self.battery_icon)
        self.battery_label = Gtk.Label()
        self.battery_label.add_css_class("battery")
        self.battery_box.append(self.battery_label)
        self.refresh_battery()
        GLib.timeout_add_seconds(20, self.refresh_battery)
        light_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bottom.set_center_widget(light_box)
        self.light_label = Gtk.Label(label="☀  Luminosité indisponible")
        self.light_label.set_xalign(0)
        light_box.append(self.light_label)
        self.slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 1)
        self.slider.set_size_request(220, -1)
        self.slider.set_draw_value(False)
        self.slider.connect("value-changed", self.light_changed)
        light_box.append(self.slider)
        self.refresh_light()
        GLib.timeout_add_seconds(20, self.refresh_light)
        power_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        power_box.set_valign(Gtk.Align.CENTER)
        bottom.set_end_widget(power_box)
        brand = Gtk.Label(label="ArchASP · Sway")
        brand.add_css_class("secondary")
        power_box.append(brand)
        for label, method in (("Redémarrer", "Reboot"), ("Éteindre", "PowerOff")):
            button = Gtk.Button(label=label)
            button.add_css_class("power")
            button.set_sensitive(not self.preview and self.can_power(method))
            button.connect("clicked", self.confirm_power, method)
            power_box.append(button)
        self.window.present()
        if not self.preview:
            # CONTRACT: le compte déjà sélectionné entre directement dans le
            # dialogue PAM ; seul le nom manuel exige une validation explicite.
            self.user_changed()
            self.selection_ready = True
            GLib.idle_add(self.begin_selected_user)

    def refresh_clock(self):
        now = datetime.now().astimezone()
        self.time.set_text(now.strftime("%H:%M"))
        self.date.set_text(now.strftime("%A %-d %B %Y").capitalize())
        return True

    def refresh_battery(self):
        state = battery()
        if state is None:
            self.battery_box.set_visible(False)
            self.battery_icon.set_text("")
            self.battery_label.set_text("")
        else:
            self.battery_box.set_visible(True)
            percent, status = state
            icon = "" if status in ("Charging", "Not charging") else ("" if percent >= 80 else "" if percent >= 40 else "")
            translated = {"Charging": "En charge", "Discharging": "Décharge", "Full": "Chargé", "Not charging": "Branché"}.get(status, status)
            self.battery_icon.set_text(icon)
            self.battery_label.set_text(f"{percent} % · {translated}")
        return True

    def refresh_light(self):
        self.light = backlight()
        if self.light is None:
            self.light_label.set_text("☀  Luminosité indisponible")
            self.slider.set_sensitive(False)
        else:
            _, maximum, current = self.light
            percent = max(10, min(100, round(100 * current / maximum)))
            self.slider.handler_block_by_func(self.light_changed)
            self.slider.set_value(percent)
            self.slider.handler_unblock_by_func(self.light_changed)
            self.slider.set_sensitive(not self.preview)
            self.light_label.set_text(f"☀  Luminosité {percent} %" + (" · aperçu" if self.preview else ""))
        return True

    def light_changed(self, *_):
        percent = round(self.slider.get_value())
        self.light_label.set_text(f"☀  Luminosité {percent} %")
        if not self.preview and self.light:
            if getattr(self, "light_timer", None):
                GLib.source_remove(self.light_timer)
            self.light_timer = GLib.timeout_add(250, self.apply_light, percent)

    def apply_light(self, percent):
        self.light_timer = None
        if self.light:
            try:
                set_brightness(self.light[0], self.light[1], percent)
            except (OSError, ValueError):
                self.refresh_light()
        return False

    def user_changed(self, *_):
        other = self.selector.get_selected() == self.selector.get_model().get_n_items() - 1
        self.manual.set_visible(other)
        if other:
            self.manual.grab_focus()
        self.refresh_avatar(self.username() if not self.preview else "")
        if not self.preview and self.flow:
            self.flow.reset()
            self.entry.set_text("")
            self.entry.set_visibility(False)
            self.entry.set_sensitive(False)
            self.button.set_label("Continuer" if other else "Connexion")
            self.prompt.set_text("Saisissez le nom utilisateur" if other else "Chargement de l’authentification…")
            self.error.set_text("")
            if self.selection_ready and not other:
                self.begin_selected_user()

    def begin_selected_user(self):
        if not self.preview and not self.busy and self.username() and self.selector.get_selected() != self.selector.get_model().get_n_items() - 1:
            self.current_user = self.username()
            self.prompt.set_text("Chargement de l’authentification…")
            self.perform(self.flow.begin, self.current_user)
        return False

    def username(self):
        if self.selector.get_selected() == self.selector.get_model().get_n_items() - 1:
            return self.manual.get_text().strip()
        return self.selector.get_selected_item().get_string()

    def refresh_avatar(self, username):
        # INVARIANT: l'image de login provient uniquement d'AccountsService,
        # avec ownership root et dimensions validées ; aucun accès au HOME.
        icon = system_icon(username)
        if icon:
            try:
                self.avatar_picture.set_paintable(Gdk.Texture.new_from_filename(str(icon)))
                self.avatar_picture.set_visible(True)
                self.avatar_fallback.set_visible(False)
                return
            except GLib.Error:
                pass
        self.avatar_picture.set_visible(False)
        self.avatar_fallback.set_visible(True)

    def submit(self):
        if self.preview or self.busy:
            return
        if self.flow.pending:
            kind = self.flow.pending["auth_message_type"]
            response = self.entry.get_text() if kind in ("secret", "visible") else None
            self.entry.set_text("")
            self.perform(self.flow.answer, response)
        else:
            username = self.username()
            if not username:
                self.error.set_text("Saisissez un nom utilisateur.")
                return
            self.current_user = username
            self.perform(self.flow.begin, username)

    def perform(self, func, *args):
        self.busy = True
        self.button.set_sensitive(False)
        self.entry.set_sensitive(False)
        self.selector.set_sensitive(False)
        def run():
            try:
                result = func(*args)
                GLib.idle_add(self.handle_reply, result)
            except Exception:
                # CONTRACT: aucune exception, requête ou réponse PAM n'est imprimée.
                GLib.idle_add(self.handle_failure)
        threading.Thread(target=run, daemon=True).start()

    def handle_reply(self, reply):
        self.busy = False
        self.selector.set_sensitive(True)
        if reply["type"] == "auth_message":
            kind = reply["auth_message_type"]
            self.prompt.set_text(reply["auth_message"])
            self.error.set_text(reply["auth_message"] if kind == "error" else "")
            self.entry.set_visible(kind in ("secret", "visible"))
            self.entry.set_visibility(kind == "visible")
            self.entry.set_sensitive(kind in ("secret", "visible"))
            self.button.set_label("Connexion" if kind == "secret" else "Valider" if kind == "visible" else "Continuer")
            self.entry.grab_focus() if kind in ("secret", "visible") else self.button.grab_focus()
        elif reply["type"] == "success":
            if self.start_called:
                try:
                    save_last_user(self.current_user)
                except OSError:
                    pass
                self.quit()
                return False
            self.start_called = True
            self.prompt.set_text("Ouverture de session…")
            self.perform(self.flow.start)
            return False
        elif reply["type"] == "error":
            self.start_called = False
            self.error.set_text("Authentification refusée. Réessayez." if reply["error_type"] == "auth_error" else "Erreur de connexion. Réessayez.")
            self.entry.set_text("")
            self.entry.set_visible(True)
            self.entry.set_sensitive(False)
            self.button.set_label("Réessayer")
        self.button.set_sensitive(True)
        return False

    def handle_failure(self):
        self.busy = False
        self.selector.set_sensitive(True)
        self.flow.reset()
        self.start_called = False
        self.entry.set_text("")
        self.entry.set_sensitive(False)
        self.error.set_text("Connexion à greetd impossible. Réessayez.")
        self.button.set_label("Réessayer")
        self.button.set_sensitive(True)
        return False

    def can_power(self, method):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
            result = bus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Can" + method, None, GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 2000)
            return result.unpack()[0] == "yes"
        except GLib.Error:
            return False

    def confirm_power(self, _button, method):
        dialog = Gtk.AlertDialog()
        dialog.set_message("Redémarrer l’ordinateur ?" if method == "Reboot" else "Éteindre l’ordinateur ?")
        dialog.set_buttons(["Annuler", "Confirmer"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self.window, None, self.power_chosen, method, dialog)

    def power_chosen(self, dialog, result, method, _dialog):
        try:
            if dialog.choose_finish(result) != 1 or self.preview or not self.can_power(method):
                return
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
            bus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", method, GLib.Variant("(b)", (False,)), None, Gio.DBusCallFlags.NONE, 2000)
        except GLib.Error:
            self.error.set_text("Action d’alimentation indisponible.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    # La session de preview peut porter une locale différente de la locale système.
    try:
        system_locale = next((line.split("=", 1)[1].strip().strip('"') for line in Path("/etc/locale.conf").read_text().splitlines() if line.startswith("LANG=")), "")
        locale.setlocale(locale.LC_TIME, system_locale or "")
    except (OSError, locale.Error):
        locale.setlocale(locale.LC_TIME, "")
    app = Greeter(preview=args.preview)
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
