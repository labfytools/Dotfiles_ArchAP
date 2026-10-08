# Configuration SwayFX

Les couleurs et variables d'apparence viennent du
[moteur commun](../../../../quickshell/.config/quickshell/labfy-sway/theme/README.md).
`theme-default.conf` assure le démarrage Mocha avant génération ;
`generated/theme.conf` est l'état runtime créé atomiquement par
`bin/.local/bin/generate-appearance.py` depuis la palette QuickShell.
`wallpaper-default.conf` définit le repli bleu `fill` ;
`generated/wallpaper.conf` redéfinit seulement `$wallpaper`. Une unique
directive `output * bg $wallpaper fill` applique le résultat. Le glob
`generated/*.conf` peut être vide et le repli reste valide. Les chemins
utilisateur contenant des espaces ou accents sont représentés par un lien
symbolique persistant à nom ASCII dans
`$XDG_CONFIG_HOME/labfy-appearance/wallpapers/`, car SwayFX 0.6 refuse
ces chemins dans une directive `output bg`, même entre guillemets.

Le compositeur actif est **SwayFX 0.6** avec `scenefx`. La session UWSM
sélectionne `sway.desktop` et charge `config` : `bind`, `input`, `rules`,
`style`, `swayfx` et `autostart`. `eDP-1` est l'unique écran configuré, à
l'origine logique. La configuration de barre native a été archivée dans
`docs/legacy/swaybar/` ; la barre et les notifications sont fournies par
QuickShell, lancé par `quickshell-labfy-sway.service`.

`autostart` lance une fois le listener IPC
`scripts/inactive-windows-transparency.py`, `limusic-app` et `autotiling`.
Ce listener réutilise les événements `window::floating` pour appliquer la
bordure serveur de 2 px lors des bascules IPC, puis restaure la bordure
antérieure au retour en mosaïque. Aucun second abonné permanent n'est lancé.
Cliphist, swayidle, wlsunset et QuickShell sont gérés par systemd user ;
aucune commande `qs` n'est lancée par Sway. Le fichier `swayfx` fixe les
animations à 0, les coins à 4, les ombres validées et le flou uniquement sur
la couche QuickShell. Les profils TLP restent accessibles par les raccourcis
`tlpctl`.

Valider avec `sway --validate` puis recharger avec `swaymsg reload`.
Le rollback manuel de la barre et des notifications est décrit dans
`quickshell/.config/quickshell/labfy-sway/notifications/ROLLBACK.md`.
