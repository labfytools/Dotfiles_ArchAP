# Fond d'écran 17C

Réglages rapides → Apparence → Fond d'écran utilise `FolderDialog` de
`QtQuick.Dialogs`, disponible dans le Qt local. Le choix d'un dossier enregistre
uniquement la préférence et relance le scan. Un clic ou Précédent/Suivant ne
fait que sélectionner et prévisualiser ; seul Appliquer passe par
`AppearanceController.applyWallpaper(path)`.

`bin/.local/bin/wallpaper-manager.py` expose `current`, `scan DIRECTORY
--page N`, `validate FILE`, `thumbnail FILE`, `set-directory DIRECTORY`,
`apply FILE` et `reconcile`. Les réponses réussies sont des objets JSON sur
stdout ; les erreurs vont sur stderr avec code non nul. Le backend n'est pas
un daemon. Chaque page charge au plus 24 images, y compris ses miniatures ;
« Voir plus » demande la page suivante. Les fichiers cassés sont sautés et
une extension ne suffit pas : Pillow doit ouvrir et décoder l'image. Formats
validés : JPEG, PNG et WebP. Les chemins via symlink restent acceptés.

Le manifeste contient `path`, `filename`, `thumbnail`, `width`, `height`,
`format`, `size`, `mtime` et `canonicalPath`. Le cache dans
`$XDG_CACHE_HOME/labfy-appearance/wallpapers/` contient des PNG de 320 px
maximum, créés par fichier temporaire puis `os.replace`. La clé SHA-256
comprend le chemin canonique, la taille, `mtime_ns` et la version du schéma
thumbnail. Au delà de 512 PNG, le backend supprime seulement les plus anciens
de ce cache jusqu'à 448 entrées ; aucune maintenance périodique n'est lancée.

Le dossier initial suit cet ordre : dernière préférence valide dans
`$XDG_CONFIG_HOME/labfy-appearance/preferences.json`, `~/.wallpapers`,
`~/Pictures/Wallpapers`, `XDG_PICTURES_DIR`, puis `$HOME`. Aucun dossier n'est
créé par cette recherche. Le mode de rendu reste `fill`.

Le fichier runtime `generated/wallpaper.conf` est distinct de
`generated/theme.conf` et n'est pas versionné. Le repli versionné Sway est
`wallpaper-default.conf`. SwayFX 0.6 ne lit pas correctement un chemin avec
espaces dans `output bg`, même cité. Le backend garde donc le chemin original
dans l'état utilisateur et crée atomiquement un symlink persistant avec un nom
ASCII sûr dans `$XDG_CONFIG_HOME/labfy-appearance/wallpapers/`. Sway lit cet
alias. Le chemin de l'utilisateur n'est jamais une commande shell.

L'application tient un verrou non bloquant, vérifie le décodage, écrit
`wallpaper.conf` par temp/flush/fsync/replace, lance `sway --validate`,
`swaymsg reload`, puis vérifie le `swaybg` effectif avant de publier
`$XDG_STATE_HOME/labfy-appearance/effective.json` en schéma 2. En cas d'échec,
elle restaure la configuration et l'état précédents puis recharge Sway.
Les champs 17B de thème restent intacts ; la révision augmente une fois par
application réussie et jamais par sélection. Les états 17B sans wallpaper
sont lus avec le fond actif de `swaybg` comme valeur initiale.

Si l'image courante disparaît, `current` signale `wallpaperMissing` sans
interrompre le rendu déjà présent. `reconcile` restaure le repli versionné au
prochain appel explicite ; un nouvel `apply` valide peut aussi la remplacer.
Le thème, Night Light et Sun Mode ne sont jamais calculés depuis l'image en
17C. L'état final validé de ce lot reste Mocha/Lavender et le fond Sway bleu.
