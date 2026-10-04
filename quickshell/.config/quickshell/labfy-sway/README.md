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
│   ├── Tray
│   ├── System Monitor
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
backlight utilise le noeud machine `amdgpu_bl1` dans `BrightnessSlider.qml` ;
le System Monitor résout dynamiquement les noeuds DRM AMD et hwmon
`k10temp`/`amdgpu` par identité, noms et labels. Les scans Wi-Fi et Bluetooth
ne sont possédés que par les pages ouvertes.

Le gestionnaire de fonds d'écran local est décrit dans
[WALLPAPER.md](controlcenter/WALLPAPER.md). Il utilise Sway et `swaybg`, sans
service permanent ni changement automatique du thème.

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
