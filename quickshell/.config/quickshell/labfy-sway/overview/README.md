# Vue d'ensemble des workspaces SwayFX

`Super+W` ouvre et ferme la surface `PanelWindow` centrée sur la sortie
focalisée. Elle affiche toujours les workspaces numérotés 1 à 10 ; un workspace
absent de l'arbre Sway est indiqué vide. Le panneau atteint au plus 1140 × 730
pixels logiques, avec 16 pixels de marge minimale. Avec cinq colonnes, sa
hauteur est de 566 pixels : la grille de 430 pixels tient dans 438 pixels
utiles sur `eDP-1`, sans défilement. Sur les petits écrans, le défilement reste
disponible si la grille dépasse réellement la hauteur utile. La surface
layer-shell `Overlay` prend le focus
clavier exclusivement pendant l'ouverture et libère ce focus en se fermant.
La surface `labfy-setting-osd` suspend seulement une nouvelle capture
automatique tant qu'elle est visible ; les miniatures déjà validées restent
disponibles.

## Gestes à trois doigts (SwayFX)

Sur le touchpad ASUS `2362:12311:ASCP1201:00_093A:3017_Touchpad`, les
`bindgesture` natifs du mode `default` déclenchent : haut → `open`, bas →
`close`, gauche → `workspace next_on_output`, droite →
`workspace prev_on_output`. Les directions désignent le mouvement physique des
doigts. Les autres nombres de doigts, dont le défilement à deux doigts, ne sont
pas liés ici. `--exact` n'est pas imposé avant l'essai matériel des diagonales.

Le script ponctuel `~/.config/sway/scripts/touchpad-gestures` choisit la sortie
du workspace focalisé à l'instant du geste. Il interroge `polkitUi state` et
ignore ces quatre gestes pendant une demande d'authentification. Haut et bas
appellent respectivement `overviewUi-<sortie> open` et `close` ; ils ne passent
pas par `toggle`. Une fermeture annule aussi l'ouverture différée après la
capture. Si l'Overview est ouverte, le dispatcher la ferme puis attend
`overviewUi-<sortie> active=false` avant de naviguer. La navigation parcourt
seulement les workspaces existants de la sortie, dans l'ordre et avec le
bouclage natifs de Sway ; aucun workspace vide n'est
créé et aucune fenêtre n'est déplacée. `Super+W` garde son `toggle`.

Ces liaisons appartiennent seulement au mode `default` : en mode `resize`, elles
ne s'exécutent pas et le mode n'est pas quitté automatiquement. Les gestes
Sway ne sont pas garantis au-dessus d'une barre layer-shell : la barre
QuickShell peut recevoir le swipe à la place du compositeur. Ce cas demande
un essai physique distinct. Le focus exclusif de l'Overview reste nécessaire
au clavier ; la réception du swipe au-dessus de ses cartes et de son fond doit
également être confirmée sur le touchpad réel.

Pour retirer uniquement ces gestes, supprimer les quatre lignes `bindgesture`
marquées dans `~/.config/sway/bind`, puis lancer `swaymsg reload`. Le dispatcher
et les opérations IPC explicites peuvent ensuite être supprimés s'ils ne sont
plus utilisés ; les raccourcis clavier et le reste de l'Overview continuent de
fonctionner.

## Politique de captures STEP15A

Les cartes utilisent immédiatement l'arbre IPC et les miniatures individuelles
valides. Seule l'ouverture de l'Overview ou un changement structurel pendant
qu'elle est visible déclenche `grim -T <foreign_toplevel_identifier>`.
La barre ne lance aucune capture périodique lorsqu'elle est fermée et la
fermeture annule sa file de travail. Les fenêtres sans image gardent la
reconstruction géométrique, leurs titres et les actions IPC existantes.
Les captures complètes de sortie ont été désactivées : elles ne permettent pas
d'exclure les pixels d'une application sensible. Leurs anciennes images sont
retirées du cache lors de la prochaine lecture de l'état.

La politique est lue dans
`$XDG_CONFIG_HOME/labfy-sway/overview-capture.json` (ou
`~/.config/labfy-sway/overview-capture.json`). L'absence de fichier autorise
les miniatures individuelles. Un fichier invalide désactive les miniatures.
Exemple pour les désactiver :

```json
{"enabled": false, "excludeApps": []}
```

Exemple d'exclusion par `app_id` Wayland ou classe XWayland :

```json
{"enabled": true, "excludeApps": ["org.keepassxc.KeePassXC", "*password*", "proton-pass"]}
```

Le motif suit `fnmatch` et ne regarde pas le titre. Il ne détecte pas toutes
les fenêtres contenant des secrets. Les règles sont relues pendant l'ouverture
et les images devenues exclues sont purgées. L'inventaire IPC des workspaces
et les fonctions focus/déplacement restent accessibles lorsque les images
sont désactivées.

Le cache privé dans `XDG_RUNTIME_DIR` refuse les chemins douteux et garde au
plus 256 fichiers reconnus et 32 Mio. Une image est limitée à 4 Mio. Un seul
lot de capture s'exécute à la fois ; chaque lot tente au plus quatre fenêtres,
avec deux secondes par fenêtre et huit secondes pour l'ensemble du helper.
Un verrouillage ferme l'Overview, annule les programmations et purge les JPEG.
Les manifestes antérieurs au verrouillage ne sont pas réutilisés au déverrouillage.
Les miniatures sont des images ponctuelles et peuvent montrer une dernière
frame ancienne d'une fenêtre cachée ; aucune carte n'est présentée comme live.
La validation multi-écran physique reste à effectuer.

## Interactions

- Clic sur une carte : activer le workspace et fermer.
- Clic sur une fenêtre : activer son workspace, focaliser son `con_id`, fermer.
- Glisser une fenêtre sur une carte : la déplacer et garder l'Overview ouverte.
- Clic droit sur une fenêtre : sélectionner « déplacer vers ».
- Flèches : choisir la carte ; `Tab` : choisir une fenêtre ; `M` : choisir une
  destination ; chiffres `1` à `9`, `0` pour `10`, puis `Entrée` : déplacer.
- `Entrée` sans mode déplacement : activer la carte ou la fenêtre choisie.
- `Échap` ou clic hors du panneau : fermer.

Le helper `backend.py` vérifie les bornes de workspace et l'existence du vrai
`con_id` dans l'arbre juste avant toute commande. Les arguments sont passés
directement à `swaymsg`, sans shell ni titre de fenêtre. Le déplacement utilise
`[con_id=N] move container to workspace number W` et ne change pas le workspace
actif. Une réponse Sway en échec laisse le panneau ouvert et relit l'arbre.
