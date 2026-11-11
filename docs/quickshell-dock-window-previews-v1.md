# QuickShell Dock — points de fenêtres et vignettes Wayland (11 novembre 2026)

## Comportement

Chaque application de la rangée du dock affiche autant de points sous son icône
qu'elle possède de fenêtres **réellement détectées par Sway**. Les icônes des
séparateurs n'affichent pas de points. Un survol intentionnel (> 330 ms) sur
une application ouverte affiche des cartes de fenêtres, avec leur **aperçu
visuel ponctuel**, leur titre et leur workspace. Cliquer une carte transmet
l'identifiant exact au mécanisme existant `FavoritesService.focusWindow()`.
Le survol seul ne déplace aucune fenêtre, ne change aucun workspace et ne
modifie jamais le focus clavier.

Au-delà de quatre cartes, le panneau défile horizontalement. L'interface
ne prend jamais le focus clavier. Après éloignement du pointeur (620 ms), le
panneau disparaît. Les menus contextuels et le déplacement des favoris ont
priorité sur les vignettes.

## Capture native, sans surveillance permanente

SwayFX sur ArchASP publie les protocoles `ext-foreign-toplevel-list-v1`,
`ext-image-copy-capture-v1` et
`ext-foreign-toplevel-image-capture-source-manager-v1`. Les fenêtres de son
arbre IPC possèdent un `foreign_toplevel_identifier` permettant une
correspondance stricte entre le clic sur une vignette et la fenêtre Sway.

QuickShell 0.3.2 ne fournit pas un `ScreencopyView` utilisable pour cette
capture individuelle sur Sway (son chemin toplevel dépend de Hyprland).
Le collecteur ponctuel en Go est fondé sur le projet MIT
`mil-ad/wlthumbs`, commit amont
`516603c3144078b4d974108b80f7e9622ee4f3c9`, avec le code et la
licence conservés sous `tools/wlthumbs/`. Le correctif local ajoute
`-ids` : la capture est refusée sans une liste explicite de 1 à 8
identifiants hexadécimaux (32 caractères), et ne capture **que** ces
fenêtres. La capture de sorties complètes est interdite dans ce mode.
Le build reproductible utilisateur, sans sudo :
`tools/build-labfy-wlthumbs.sh`, installe le binaire dans
`~/.local/libexec/labfy-wlthumbs`.

Le wrapper `bin/dock-thumbnails.py` valide une seconde fois tous les
identifiants Sway et étrangers, limite le nombre de captures à 8 et la
taille des PNG, impose un dossier de session `0700` dans
`$XDG_RUNTIME_DIR/labfy-dock-window-thumbnails` et restitue seulement
les URI des images validées. Le nettoyage est déclenché après fermeture
du panneau, ainsi qu'à chaque nouvelle capture. Aucune capture
permanente, périodique, en arrière-plan ou à la déconnexion n'est créée.
En cas d'échec d'un aperçu, la carte affiche l'icône de l'application,
le titre et le workspace ; la sélection reste fonctionnelle.

## Compatibilité et sécurité

- Les favoris partagés, les séparateurs, le modèle d'applications et le menu
  QuickShell existant conservent leur format.
- La récupération des fenêtres réutilise le snapshot IPC Sway existant,
  sans nouvelle boucle de polling.
- La capture est limitée à la demande de l'utilisateur, et les noms des
  fenêtres ne sont pas utilisés pour décider de leur identité.
- La couche du dock conserve `WlrKeyboardFocus.None`,
  `exclusionMode.Ignore`, `exclusiveZone: 0` et la bande d'activation
  de 4 px sur toute la largeur.
- Les PNG locaux constituent des données sensibles ; ils résident seulement
  dans le runtime privé et sont supprimés à la fermeture du panneau.
- Les vignettes ne modifient pas Session Restore V2, l'autostart ni les
  raccourcis Sway.

## Validation

- Tests unitaires `tests/dock/test_thumbnails.py` : entrées bornées,
  captures sélectives, permissions, nettoyage et refus des chemins suspects.
- `tests/dock/headless.py` : vrai SwayFX et vrai QuickShell isolés,
  trois fenêtres Kitty pour trois points et trois cartes sélectionnables,
  non-vol de focus, captures réelles de la session de test, nettoyage, et
  anciens scénarios de dock.
- Test non destructif sur ArchASP : sélection de trois fenêtres Firefox,
  production de trois PNG temporaires puis nettoyage, sans changement
  de focus ; ne conserve pas leur contenu.
- `qmllint`, suites applications/dock, chargement du shell complet et
  compatibilité Session Restore V2.

Les artefacts de test générés sont dans le cache privé de développement,
pas dans le dépôt. Aucun média de la session de travail n'est publié.
