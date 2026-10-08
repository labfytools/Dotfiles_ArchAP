# QuickShell labfy-sway

Le [moteur de thème commun](theme/README.md) fournit les couleurs effectives
à QuickShell et Sway/SwayFX depuis une seule palette Catppuccin versionnée.

Barre principale et serveur de notifications de la session SwayFX.

```text
Bar
├── Workspaces
├── Window/task switcher
├── Date Center
│   ├── MPRIS
│   └── Notifications
├── Right Status
│   ├── Network
│   ├── Bluetooth
│   ├── Battery
│   ├── Updates
│   ├── Supports amovibles
│   ├── Tray
│   └── Control Center
└── Control Center
    ├── Wi-Fi
    ├── Bluetooth
    ├── Volume
    ├── Brightness
    ├── Power Profile
    ├── Apparence
    │   └── Fond d'écran
    ├── Battery limit
    └── Session
```

`quickshell-labfy-sway.service` est activé par
`wayland-session@sway.desktop.target`, sans autostart Sway parallèle.
`NotificationService.qml` possède `org.freedesktop.Notifications` ; l'historique
est écrit hors Git via `Quickshell.statePath("notifications.json")` dans
`~/.local/state/quickshell/`. Mako demeure installé, inactif et masqué ; voir
[ROLLBACK.md](notifications/ROLLBACK.md).

`labfy-quickshell-updates.timer` exécute `bin/check-updates.py`, qui publie un
état JSON dans `$XDG_RUNTIME_DIR`. `batlimit` (CLI) et Réglages rapides →
Batterie (GUI) passent par `/usr/local/sbin/batlimit-set`. Le seuil courant
est 60 % ; le helper root est documenté dans `bin/root/README.md`.

Dépendances essentielles : `quickshell`, SwayFX 0.6, `scenefx`, une Nerd Font,
NetworkManager, BlueZ, PipeWire, TLP/`tlpctl`, `checkupdates`, `yay`, `df`,
`python3`, `swaylock` et le helper batterie pour le réglage du seuil. Le
backlight utilise le noeud machine `amdgpu_bl1` dans `BrightnessSlider.qml`.
Les scans Wi-Fi et Bluetooth
ne sont possédés que par les pages ouvertes.

Le gestionnaire de fonds d'écran local est décrit dans
[WALLPAPER.md](controlcenter/WALLPAPER.md). Il utilise Sway et `swaybg`, sans
service permanent ni changement automatique du thème.

## Supports amovibles

`RemovableMediaIndicator.qml` affiche dans la zone d'état un indicateur
lorsqu'au moins un système de fichiers éligible est présent. Son `PopupWindow`
natif liste les volumes, leur état et les erreurs publiées, puis offre les
actions **Ouvrir**, **Monter** ou **Démonter**, et **Retirer en sécurité** si
le lecteur le permet. Ouvrir lance Yazi dans Kitty via UWSM. Le popup participe
à la même exclusion mutuelle que le Date Center, le menu des fenêtres et le
Control Center.

QuickShell lit exclusivement le snapshot JSON V1
`$XDG_RUNTIME_DIR/labfy-removable-media.json`. Il refuse intégralement un
snapshot dont `schema` n'est pas `labfy.removable-media`, dont `version` n'est
pas `1`, ou dont les appareils ne respectent pas le contrat attendu. Les
commandes passent sans shell à `labfy-removable-mediactl`, qui est l'unique
frontière de commande vers le daemon ; le socket Unix associé est privé (`0600`).

Le service utilisateur repose sur l'ObjectManager UDisks et ne présente que
les systèmes de fichiers USB ou SD/MMC. Les blocs marqués `HintIgnore` ou
`HintSystem` sont exclus. Un volume `crypto_LUKS` n'est ni présenté ni
déverrouillé automatiquement. Les périphériques MTP ne fournissent pas ce
modèle UDisks de système de fichiers et ne sont donc pas pris en charge. Chaque
objet UDisks présent peut être monté automatiquement une seule fois ; après un
démontage manuel, il reste démonté jusqu'à sa disparition puis sa réinsertion.
Le retrait en sécurité agit au niveau du lecteur et vérifie que ses systèmes de
fichiers sont démontés avant l'éjection ou la mise hors tension.

Le contrôle visuel synthétique peut être activé avec
`LABFY_REMOVABLE_MEDIA_TEST_STATE` (`0`, `mounted`, `unmounted` ou
`busy-error`) dans le processus QuickShell. Ces états ne lancent aucune
commande. Les tests Python synthétiques du daemon et de son IPC sont décrits
dans [systemd.md](../../../../docs/systemd.md#supports-amovibles-usbsd).

Cette fonction est indépendante de Session Restore : elle ne lit ni n'écrit de
checkpoint de session et n'intervient pas dans son démarrage.

La validation sur matériel USB/SD réel n'a pas encore été effectuée ; l'état
actuel est couvert par les tests synthétiques seulement.

## Parité avec i3status-rs

| Ancien bloc | QuickShell |
| --- | --- |
| scratchpad indicator | volontairement non repris |
| focused_window | WindowStrip |
| music | Date Center MPRIS |
| bluetooth | status + Control Center |
| net | status + Control Center |
| sound | Control Center |
| backlight | Control Center |
| battery | status + page Batterie |
| TLP | PowerProfile |
| packages | Updates |
| time | Clock / Date Center |
| menu | page Session |
