# Synchronisation des thèmes applicatifs 17G

## Contrat et architecture

`$XDG_STATE_HOME/labfy-appearance/effective.json` est la seule source des
choix applicatifs. `appearance-app-sync.py reconcile` consomme uniquement
`effectiveFlavor`, `effectiveAccent`, `effectiveDark`,
`effectiveHighContrast`, `effectiveMode` et `revision`. Il rejette un schéma
absent, invalide ou incohérent avant toute modification. Il ne lit ni les
coordonnées, ni les lieux sauvegardés, ni l'analyse du wallpaper.

Le synchroniseur prend un verrou `app-sync.lock`, relit l'état après chaque
passage des adaptateurs et ne publie `last-applied.json` qu'avec la dernière
révision observée. Le résultat contient un statut indépendant par adaptateur.
Les fichiers générés sont écrits par fichier temporaire, `fsync`, puis
`os.replace`. Les palettes Qt et Kitty viennent toutes de
`quickshell/.config/quickshell/labfy-sway/theme/catppuccin.json`.
Les trois fichiers de palettes générés sont ignorés par Git et recréés par
le service à la réconciliation ; seuls les points d'entrée sont versionnés.

`labfy-appearance-app-sync.path` observe `effective.json` et déclenche le
service one-shot. Le service est aussi voulu par la cible de session UWSM,
ce qui réconcilie après login. Aucun polling ni daemon Python. Les limites
de fréquence systemd sont désactivées pour accepter les rafales de révisions ;
le verrou sérialise les exécutions. Une panne d'un adaptateur est enregistrée
sans bloquer les suivants. `last-applied.json` hors Git contient la révision,
les résultats et un timestamp ; il ne contient pas de lieu.

## État de départ audité le 5 octobre 2026

| Écosystème | État réellement constaté |
| --- | --- |
| GTK | `gsettings` demandait `catppuccin-mocha-lavender-standard+default` et `prefer-dark`. Seul `~/.themes/Catppuccin-Mocha` était présent ; son `index.theme` et son CSS utilisent Rosewater. Le nom demandé ne correspondait pas au répertoire installé. |
| Qt | `qt5ct` et `qt6ct` installés, palettes Mocha fixes ; `QT_QPA_PLATFORMTHEME` absent de l'environnement systemd de session. |
| Kitty | 0.49.2, instance active, include Mocha fixe, opacité implicite 1.0. |
| Neovim | 0.12.5, plugin Catppuccin, `init.lua` et lualine fixés sur Mocha. |
| Firefox avant migration utilisateur | 157.0, profil actif identifié par `profiles.ini`, thème intégré Dark (`firefox-compact-dark@mozilla.org`), contenu forcé clair par `layout.css.prefers-color-scheme.content-override=1`. Aucun `user.js`, `userChrome.css` ou `userContent.css` trouvé. Aucun profil n'est modifié par 17G. |

## Capacités et limites

| Application | Light/Dark | Flavor exact | High Contrast | Live |
| --- | --- | --- | --- | --- |
| GTK classique | oui via `gsettings` | Mocha installé avec Rosewater ; autres flavors absents, fallback Adwaita | partiel : préférence et thème clair/sombre ; aucune variante Catppuccin HC installée | nouvelles fenêtres ; recharge des fenêtres existantes selon application |
| GTK4/libadwaita | préférence système Light/Dark | thème custom non garanti pour libadwaita | non démontré | selon application |
| Qt5/Qt6 | oui | quatre palettes générées Lavender | pas de palette HC distincte | nouvelles applications ; redémarrage possible des instances ouvertes |
| Kitty | oui | quatre flavors depuis la palette unique | fond opaque 1.0 ; déjà opaque en mode normal | SIGUSR1 documenté, envoyé aux processus Kitty du même utilisateur |
| Neovim | oui | quatre flavors Catppuccin | Visual/Search/StatusLine/séparateurs adaptés, sans dimming | `uv.fs_event`, testé sans redémarrage |
| Firefox actuel | oui : thème Proton 1.1 à deux palettes et apparence des sites Auto | aucun flavor Catppuccin | non | chrome sans redémarrage ; page locale actualisée lors du test |

Pour GTK, `Catppuccin-Mocha` est le répertoire réellement présent. Latte,
Frappé et Macchiato Lavender n'étaient pas installés ; l'adaptateur choisit
Adwaita pour ne pas publier un nom de thème inexistant. Installer des variantes
auditées de [Catppuccin GTK](https://github.com/catppuccin/gtk) est un travail
distinct. Un thème GTK custom ne recolore pas automatiquement libadwaita.

`uwsm/.config/uwsm/env` exporte `QT_QPA_PLATFORMTHEME=qt5ct`. Sur cette
machine, le plugin Qt6 expose aussi la clé `qt5ct` ; les deux versions ont été
observées ouvrant leurs plugins et leurs palettes générées avec `strace`.
Un nouveau login est nécessaire pour que tous les lanceurs et processus de
session héritent de cette variable. L'environnement systemd/DBus courant a
été mis à jour pour les nouvelles applications lancées par ces services.

Kitty inclut `generated-appearance.conf` ; le synchroniseur envoie SIGUSR1
après chaque publication. La documentation locale Kitty 0.49.2 confirme ce
signal de rechargement. Le synchroniseur n'ouvre aucun socket de contrôle.
L'opacité normale préexistante était 1.0 ; Sun Light et Sun Dark restent à 1.0.

Neovim lit l'état avant de choisir son premier colorscheme, puis surveille
le répertoire de `effective.json` pour les renommages atomiques. Un état absent
ou invalide retombe sur Mocha sans bloquer l'éditeur. Le watcher est fermé à
`VimLeavePre`. `lazy-lock.json` préexistant reste hors chantier.

Firefox consulte la préférence système/portail quand le thème actif prend
en charge les deux palettes et que le contenu est configuré sur Auto. Le portail existant
`xdg-desktop-portal-gtk` a renvoyé `1` en sombre et `2` en Sun Light.
La [source Mozilla](https://searchfox.org/firefox-main/source/modules/libpref/init/StaticPrefList.yaml)
définit l'override contenu `0=Dark`, `1=Light`, `2=Auto`. La migration doit
être faite dans l'interface Firefox : choisir un thème compatible avec les
deux palettes, dont le thème intégré **System** ou le Proton 1.1 audité, et
l'apparence des sites **Automatic**, puis vérifier localement
`matchMedia('(prefers-color-scheme: dark)').matches` en Mocha, Sun Light et
Sun Dark. Le chrome et le contenu doivent être contrôlés séparément. Aucune
écriture de `prefs.js`, base SQLite ou fichier d'extensions n'est permise
pendant que Firefox est ouvert.

Avant la migration, une page HTML locale a été ouverte dans le profil actif et a affiché
`light` en Mocha, Sun Light **et** Sun Dark. Ce test confirme que le contenu
ne suivait alors pas la préférence système. La fenêtre de test a été fermée.

## Validation de migration du 5 octobre 2026

Après les changements manuels dans Firefox, le profil actif découvert par
`profiles.ini` indique `proton-theme@mozilla.org`, et ne contient
plus de préférence `layout.css.prefers-color-scheme.content-override` :
la valeur par défaut Auto vaut 2. Le thème intégré **System** n'est donc pas
le thème actif, malgré le choix annoncé dans l'interface. Le manifeste local
du thème Proton 1.1 possède `theme` et `dark_theme`. Les essais réels ont
montré que son chrome suit la préférence du portail : sombre en Mocha normal,
clair en Sun Light, sombre en Sun Dark, sans redémarrage. La page HTML locale
a rendu `dark`, `light`, `dark` ; lors du premier passage en Sun Light, un
rechargement a accéléré l'observation de `light`. Lors du second passage, la
page déjà ouverte a basculé après un délai sans rechargement. Le portail
a rendu respectivement 1, 2, 1. L'adaptateur accepte donc ce thème précis
comme intégration Light/Dark système, tout en signalant son identifiant réel.
Il ne lit que `profiles.ini` et `prefs.js` et n'écrit aucun fichier Firefox.
Le thème Proton n'est pas littéralement le thème intégré **System** ; cette
nuance n'empêche pas la synchronisation Light/Dark observée.

## Vérification et retour arrière

Les transitions Mocha → Latte → Sun Light → Sun Dark → Frappé → Macchiato →
Mocha ont produit des résultats indépendants pour les cinq adaptateurs.
GTK a basculé `prefer-dark`/`prefer-light`, Qt et Kitty ont généré les bonnes
palettes, Neovim a basculé live vers Latte, et le portail a publié `1`/`2`.
Des captures de Thunar GTK3, qt5ct, qt6ct, Kitty, Neovim et Firefox en Mocha
et Sun Light ainsi que des vues globales sont conservées dans
`~/.local/state/labfy-appearance/captures/17g/` avec permissions privées.
Thunar et les fenêtres de configuration Qt montrent le basculement visuel
clair/sombre ; Kitty et Neovim montrent Latte. Une trace d'ouverture GTK4
confirme que `~/.themes/Catppuccin-Mocha/gtk-4.0/gtk.css` est réellement lu
en Mocha. Avant la migration, Firefox conservait le chrome sombre en Sun Light ;
après la migration, il passe au chrome clair. La validation
de lisibilité physique en extérieur reste à faire par l'utilisateur ; une
capture ne la remplace pas.

Validation automatisée finale : 63 tests Python, `py_compile`, `luac -p`,
démarrage Neovim headless, `qmllint` sur 52 QML,
`systemd-analyze --user verify` et `git diff --check`.
L'instance Neovim ouverte est passée à Latte via `fs_event`. Une rafale de
six changements a laissé le `.path` actif avec la dernière révision publiée.
Une réconciliation mesurée a duré environ 73 ms sur cette machine.

Pour désactiver :

```sh
systemctl --user disable --now labfy-appearance-app-sync.path labfy-appearance-app-sync.service
```

Réappliquer l'état courant après une installation ou un redémarrage :

```sh
~/.local/bin/appearance-app-sync.py reconcile
```

Les configurations générées restent utilisables sans le service. Pour
retrouver les chemins initiaux, rétablir l'include Kitty
`kitty-themes/themes/mocha.conf`, les deux `color_scheme_path` vers
`catppuccin-mocha-lavender.conf`, supprimer l'export UWSM et choisir
explicitement Mocha dans Neovim. Réactiver le service se fait avec
`systemctl --user enable --now` pour les deux unités.
