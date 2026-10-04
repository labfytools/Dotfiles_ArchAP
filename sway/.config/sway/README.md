# Configuration SwayFX

Le compositeur actif est **SwayFX 0.6** avec `scenefx`. La session UWSM
sélectionne `sway.desktop` et charge `config` : `bind`, `input`, `rules`,
`style`, `swayfx` et `autostart`. `eDP-1` est l'unique écran configuré, à
l'origine logique. La configuration de barre native a été archivée dans
`docs/legacy/swaybar/` ; la barre et les notifications sont fournies par
QuickShell, lancé par `quickshell-labfy-sway.service`.

`autostart` lance une fois le listener IPC
`scripts/inactive-windows-transparency.py`, `limusic-app` et `autotiling`.
Cliphist, swayidle, wlsunset et QuickShell sont gérés par systemd user ;
aucune commande `qs` n'est lancée par Sway. Le fichier `swayfx` fixe les
animations à 0, les coins à 4, les ombres validées et le flou uniquement sur
la couche QuickShell. Les profils TLP restent accessibles par les raccourcis
`tlpctl`.

Valider avec `sway --validate` puis recharger avec `swaymsg reload`.
Le rollback manuel de la barre et des notifications est décrit dans
`quickshell/.config/quickshell/labfy-sway/notifications/ROLLBACK.md`.
