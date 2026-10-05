# Moteur d'apparence 17B

`catppuccin.json` est la **seule source versionnée complète** des quatre
palettes. Les 26 valeurs de chaque flavor ont été importées sans modification
depuis [Catppuccin Palette v1.8.0](https://github.com/catppuccin/palette/blob/v1.8.0/palette.json),
révision `07d02aa110ef9eb7e7427afca5c73ba9cf7f8ebd`, le 4 octobre 2026.
Le JSON local conserve seulement les noms et valeurs hex, sans les métadonnées
RGB/HSL/OKLCH de l'amont.

```text
catppuccin.json (versionné)
  → AppearanceController.qml (API live, état publié par le backend)
  → Theme.qml (singleton effectif, rôles UI)
  → composants QuickShell

catppuccin.json (versionné)
  → generate-appearance.py (rendu versionné)
  → wallpaper-manager.py (transaction 17D)
  → generated/theme.conf (runtime, ignoré par Git)
  → Sway/SwayFX
```

`Theme.qml` lit le JSON une fois au chargement par `FileView` avec
`blockLoading: true`, sans processus externe, relecture par frame ou polling.
`AppearanceController.qml` détient l'état effectif du bureau :
`effectiveFlavor`, `effectiveMode`, `effectiveDark`,
`effectiveHighContrast`, `effectiveAccent`, `revision`. Le backend persiste
l'état effectif dans `$XDG_STATE_HOME/labfy-appearance/effective.json` avec
écriture atomique, puis le contrôleur le relit au démarrage. En 17B,
`effectiveMode` vaut `normal`, `effectiveHighContrast` vaut `false`, et la
révision augmente une fois par changement accepté. `effectiveDark` est
publié par le contrôleur pour les futurs consommateurs GTK, Qt, Kitty,
Neovim, Firefox et autres ; ces applications n'auront pas à déduire le mode
clair/sombre de la palette. Sun Light et Sun Dark viendront plus tard.
`Theme.qml` consomme cet état et expose les couleurs et rôles QuickShell.
Le flavor initial est Mocha et l'accent initial Lavender. `panelOpacity = 235/255`
recrée le fond de barre historique ; un profil ultérieur peut le rendre opaque.
`onAccent` choisit noir ou blanc technique par luminance WCAG. Lavender Latte
n'atteint pas 4,5:1 avec une couleur Catppuccin ; le noir atteint environ
6,6:1. Le texte nu accentué prend `text` en Latte pour rester lisible.

Les 34 usages historiques de Mauve ont été classés par rôle : sélection,
focus, indicateur ou contrôle utilisent maintenant l'accent principal
Lavender. Les séries CPU/RAM du System Monitor restent intentionnellement
Mauve. Ce choix rend les contrôles historiques Mauve légèrement plus bleus
qu'avant. Les trois anciens Lavender restent l'accent principal.

L'API de thème est `AppearanceController.setManualFlavor(flavor)` et
`AppearanceController.setThemeMode(mode)` ; l'IPC
`qs -c labfy-sway ipc call appearance effectiveState` expose l'état complet
et `qs -c labfy-sway ipc call appearance setTheme mocha lavender` déclenche
la même application persistante en mode Manuel. La commande unifiée depuis
le dépôt est :

```sh
python bin/.local/bin/generate-appearance.py latte --accent lavender --apply
```

`--apply` délègue au gestionnaire d'apparence 17D et exige Manuel/Lavender ;
le rendu hors ligne reste disponible pour les autres accents. Ce backend
prépare les fichiers, valide Sway, recharge, persiste l'état effectif, puis
publie dans QuickShell. En cas d'échec il compense l'application. Le wallpaper
reste séparé dans `generated/wallpaper.conf` ; voir
[WALLPAPER.md](../controlcenter/WALLPAPER.md). `generate-appearance.py`
préserve les champs wallpaper du schéma effectif 3 lors d'un changement de
thème. L'algorithme Auto, ses seuils et la migration sont documentés dans
[AUTO_THEME.md](AUTO_THEME.md).
La lumière nocturne 17E est indépendante du flavor et du fond ; son service,
ses modes et ses préférences sont décrits dans [NIGHT_LIGHT.md](NIGHT_LIGHT.md).
Le repli versionné `sway/theme-default.conf` fournit Mocha même avant toute
génération. Ses quelques variables sont un artefact dérivé, pas une palette
complète indépendante. `sway/style` inclut le repli, puis un glob de fichier
runtime ; Sway accepte ce glob vide après un nouveau clone/Stow.

Les ombres `#00000055` et `#00000035` sont des valeurs de profil structurelles,
pas des couleurs Catppuccin. La transparence inactive reste 0,85 ; le
générateur fournit une variable Sway pour le futur profil Sun Mode.
