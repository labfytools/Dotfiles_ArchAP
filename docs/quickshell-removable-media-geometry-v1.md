# Supports amovibles : géométrie dynamique, V1

Investigation du 21 octobre 2026, Arch Linux, SwayFX, écran eDP-1 à échelle
fractionnaire 1,4, Quickshell 0.3.2-1, Qt 6.12.0.

## Cause démontrée

Le modèle JSON est correctement chargé et les delegates sont correctement
créés. Dans la reproduction initiale, QML mesure un popup de 400 × 161 pour
Ventoy, puis 400 × 279 pour Ventoy + PHOTO_BAK ; chaque carte mesure 376 × 108.
Pourtant, la capture après ajout montre toujours UNE carte Ventoy étirée
verticalement. Les tailles de police QML restent 14 et 11 pixels ; les boutons
mesurent toujours 30 pixels de haut.

La trace `WAYLAND_DEBUG=1` identifie la collision :

```text
wp_viewport.set_destination(400, 279)
xdg_popup.reposition(positioner, 1)   # Qt
xdg_popup.reposition(positioner, 0)   # Quickshell
xdg_popup.repositioned(0)            # seule réponse observée
xdg_popup.configure(..., 400, 279)
```

Après cette séquence, aucun nouveau buffer de la surface du popup n'est
attaché. Le compositeur affiche donc l'ancien buffer dans le nouveau viewport.
Cela produit une déformation du rendu, sans changement de la police logique.

Dans Qt 6.12, `QWaylandXdgSurface::Popup::reposition()` incrémente
`m_waitingForRepositionSerial`, positionne `m_waitingForReposition = true`, et
`isExposed()` renvoie false tant que cette attente subsiste. Seul le retour du
jeton attendu lève cette attente. En parallèle, Quickshell 0.3.2 envoie une
requête directe avec le jeton constant zéro. SwayFX peut remplacer la requête
précédente par cette dernière : Qt ne reçoit pas le jeton qu'il attend.

Fermer le popup détruit sa fenêtre native (`deleteOnInvisible()` de
`ProxyPopupWindow`) et son rôle `xdg_popup`. Rouvrir crée un nouvel état Qt,
sans attente orpheline, et un buffer à la bonne taille. C'est la raison précise
de la réparation apparente par fermeture/réouverture.

Les `forceLayout()`, le délai de 60 ms et le remplacement de `Flow` par `Row`
ne réparent pas cette attente du protocole. Un positionneur peut calculer une
bonne taille alors que Qt bloque les nouveaux rendus. Le défaut peut aussi
empêcher les phases de polish suivantes de terminer, laissant alors certaines
mesures de positionneurs périmées.

Sources primaires :

- [Quickshell 0.3.2, positionnement Wayland](https://github.com/quickshell-mirror/quickshell/blob/v0.3.2/src/wayland/popupanchor.cpp)
- [Quickshell 0.3.2, cycle de vie du popup](https://github.com/quickshell-mirror/quickshell/blob/v0.3.2/src/window/popupwindow.cpp)
- [Qt 6.12, repositionnement et exposition xdg-shell](https://github.com/qt/qtbase/blob/v6.12.0/src/plugins/platforms/wayland/plugins/shellintegration/xdg-shell/qwaylandxdgshell.cpp)

## Correction

`tools/quickshell/qt612-popup-owner.patch` conserve les propriétés d'ancrage de
Quickshell et confie le repositionnement à
`QWaylandShellSurface::setWindowGeometry()` pour Qt >= 6.12. Qt possède ainsi
les requêtes ET leur acquittement ; aucun jeton brut zéro ne vient remplacer
ses jetons. La surface reste ouverte et peut réellement être redimensionnée.
Aucune taille de fenêtre fixe supplémentaire, aucun timer de rendu et aucune
fermeture/réouverture automatique.

Ce correctif est dans le moteur, car une modification du composant QML seul
ne peut pas réparer proprement cet état privé de Qt. Il est compilé avec les
headers privés de la version Qt installée ; aucune bibliothèque système n'est
remplacée et aucune structure ABI n'est manipulée.

`tools/build-quickshell-popup-fix` utilise les archives Quickshell 0.3.2 et
CLI11 2.5.0 avec SHA-256 vérifiés, deux compilations simultanées au maximum et
une installation privée dans `~/.local/opt/quickshell-qt612-popup`. Le script
est volontairement limité à Qt 6.12.x, version étudiée. Relancer ce script
après chaque mise à jour Qt. Le lanceur `labfy-quickshell` refuse un binaire
compilé pour une autre version Qt.

Dans `RemovableMediaIndicator.qml`, retrait des tentatives de relayout,
restauration de `Flow`, maintien de l'ancre tant que le popup est ouvert et
message « Aucun support amovible » pour la liste vide. Le popup reste ouvert
pour permettre la réapparition d'un support. Le protocole JSON, le backend et
les commandes de stockage restent inchangés.

## Test reproductible

```sh
~/.dotfiles/tools/build-quickshell-popup-fix
python ~/.dotfiles/quickshell/.config/quickshell/labfy-sway/tests/removable_geometry/wayland.py \
  --qs ~/.local/opt/quickshell-qt612-popup/bin/quickshell \
  --artifacts /tmp/removable-geometry-validation
```

Le test nécessite une session SwayFX active, `grim` et Pillow. Il copie le
renderer dans le répertoire d'artefacts, redirige uniquement cette copie vers
un snapshot temporaire, neutralise `runAction()` et utilise les modes
TEST_ONLY des popups Impression/Sauvegarde. Aucun snapshot de production,
montage, démontage, éjection ou sauvegarde réelle n'est modifié.

Trois cycles successifs : Ventoy → Ventoy + PHOTO_BAK → Ventoy → non monté →
aucun → Ventoy. Le popup n'est jamais fermé pendant ces 18 étapes. Le test
vérifie les dimensions effectives, les polices, l'absence de chevauchement ou
de débordement des boutons et la hauteur exacte du contenu. Il compare
ensuite chaque capture Wayland à une référence de même état après réouverture.
C'est cette comparaison qui détecte un ancien buffer étiré malgré de bonnes
propriétés QML. Tolérance : moins de 0,1 % des pixels diffèrent de plus de
24 niveaux par canal et erreur moyenne maximale par canal < 1/255. La
variation des contours de rectangles après un aller-retour de taille à
l'échelle 1,4 atteint 16/255 dans les captures des supports, sans différence
dans les glyphes. Pour les popups voisins, la comparaison utilise la même limite d'erreur
moyenne ; le nombre de pixels différents est enregistré sans seuil, car les
positions fractionnaires de leurs glyphes changent l'anticrénelage.

Les popups Impression et Sauvegarde sont également testés dynamiquement puis
comparés à des références après réouverture. Le fichier `wayland.log` permet
de vérifier les jetons et les nouveaux buffers réellement publiés.

## Résultats

Validation concluante avec le binaire installé, lancé via `labfy-quickshell`.

| État (trois cycles) | Fenêtre logique | Cartes |
| --- | --- | --- |
| Ventoy | 400 × 161 | 1 × (376 × 108) |
| Ventoy + PHOTO_BAK | 400 × 279 | 2 × (376 × 108) |
| Retour à Ventoy | 400 × 161 | 1 × (376 × 108) |
| Ventoy non monté | 400 × 161 | 1 × (376 × 108) |
| Aucun support | 400 × 67 | aucune |
| Réapparition de Ventoy | 400 × 161 | 1 × (376 × 108) |

Les 18 étapes restent sur la même surface, visible en permanence. Polices
14/11 pixels, boutons 30 pixels de haut, espacements et bornes vérifiés.
Les 18 comparaisons de captures des supports passent : aucun pixel ne diffère
de plus de 24/255 ; erreur moyenne maximale par canal 0,444/255.

Dix transitions des popups voisins passent aussi, avec captures complètes :
Impression (`empty`, `jobs`, `unavailable`, `empty`) et Sauvegarde (`idle`,
`copying`, `error`, `success`, `unmounted`, `idle`). Erreur moyenne maximale
0,684/255. Contrôle visuel des états multiples, non monté, vide, impression
et sauvegarde ; pas de texte ou bouton étiré, tronqué ou superposé.

Le binaire Arch d'origine, avec le même QML corrigé et le même test, échoue :
le premier remplacement de snapshot peut laisser le Flow à 180 pixels de haut
et les boutons sur trois lignes. Le problème est donc indépendant des
modifications du layout QML. La reproduction initiale avec les anciens
correctifs montrait aussi l'ancienne carte étirée malgré des mesures correctes.

`qmllint` passe sans diagnostic pour les trois indicateurs. `git diff --check`,
la syntaxe Bash des deux lanceurs et l'application à blanc du patch passent.
Compilation complète et installation privée réussies. Le service Quickshell
utilise désormais ce binaire ; son journal confirme `Configuration Loaded`.
Les avertissements de découverte I3 utilisent le repli habituel sur SWAYSOCK.

Preuves persistantes :
`~/.local/state/labfy-removable-geometry-v1/` :

- `after.png` : défaut initial, une seule carte étirée après ajout ;
- `reopened-settled.png` : même état réparé par réouverture ;
- `baseline.log` : collision des jetons et absence de nouveaux buffers ;
- `stock-final/` et `stock-final.log` : échec avec le moteur Arch d'origine ;
- `validated/measurements.json` : dimensions des 18 étapes ;
- `validated/pixel-comparison.json` et `validated/other-popups.json` : comparaisons ;
- `validated/*.png` : captures dynamiques et références ;
- `validated/wayland.log` : jetons Qt acquittés et buffers effectivement renouvelés ;
- `build.log` et `rebuild.log` : compilation locale.

## Limites et maintenance

Aucune action sur les supports réels n'a été effectuée. Le branchement physique
et les commandes de montage/démontage/éjection restent à vérifier manuellement
au besoin ; leur implémentation n'a pas changé. La validation porte sur
SwayFX, Qt 6.12.0, un écran à échelle 1,4, et les deux popups voisins cités.
Les autres compositeurs, échelles, déplacements entre écrans et l'ensemble
des autres popups ne constituent pas une matrice validée exhaustivement.

Après une mise à jour Qt, recompiler avec
`~/.dotfiles/tools/build-quickshell-popup-fix`, puis relancer
`quickshell-labfy-sway.service`. Le lanceur refuse une ancienne compilation
pour éviter un décalage avec l'ABI privée Qt. Le binaire `/usr/bin/qs` reste
inchangé et conserve le défaut ; lancer directement ce binaire pour une
nouvelle instance contourne le correctif local.

Statut : `QUICKSHELL_REMOVABLE_MEDIA_GEOMETRY_V1=READY_FOR_REAL_TEST`.
