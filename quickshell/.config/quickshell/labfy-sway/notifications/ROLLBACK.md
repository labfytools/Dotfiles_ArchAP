# Serveur de notifications QuickShell : retour à Mako

État normal : `quickshell-labfy-sway.service` est activé par
`wayland-session@sway.desktop.target`. `mako.service` est masqué dans
`~/.config/systemd/user/mako.service` pour bloquer aussi son activation D-Bus
par `/usr/share/dbus-1/services/fr.emersion.mako.service`.

Le stockage QuickShell est dans
`~/.local/state/quickshell/by-shell/eba3734a789a60d49598797b9c87ae6f/notifications.json`.
L'import brut Mako est dans `~/.local/state/quickshell/labfy-sway/mako-import.json`.
Ces fichiers ne sont pas effacés lors du retour à Mako.

Pour revenir à Mako :

```sh
systemctl --user stop quickshell-labfy-sway.service
systemctl --user disable quickshell-labfy-sway.service
systemctl --user unmask mako.service
systemctl --user start mako.service
busctl --user status org.freedesktop.Notifications
```

Le propriétaire D-Bus doit afficher `Comm=mako`. Ne lancez pas la
configuration `labfy-sway` pendant ce retour à Mako : son serveur de
notifications réclamerait le même nom. Le retour à Mako est indépendant du
retour à Swaybar décrit ci-dessous.

Pour reprendre QuickShell :

```sh
systemctl --user stop mako.service
systemctl --user mask mako.service
systemctl --user enable quickshell-labfy-sway.service
systemctl --user start quickshell-labfy-sway.service
busctl --user status org.freedesktop.Notifications
```

## Retour à Swaybar + i3status-rs

Réinstaller d'abord le paquet supprimé :

```sh
sudo pacman -S i3status-rust
```

Copier `docs/legacy/swaybar/i3status-config.toml` dans
`~/.config/i3status-rust/config.toml` et `docs/legacy/swaybar/bar` dans
`~/.config/sway/bar` depuis le dépôt, puis ajouter temporairement
`include ~/.config/sway/bar` dans `~/.config/sway/config`. Exécuter :

```sh
sway --validate
swaymsg reload
```

Swaybar et son enfant i3status-rs doivent revenir. Pour arrêter QuickShell,
appliquer aussi la procédure Mako ci-dessus afin de conserver un serveur de
notifications. Ce retour est manuel et provisoire ; les fichiers archivés ne
sont plus des packages Stow actifs.
