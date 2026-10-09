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

## Provenance des miniatures

`grim -o <sortie> -s 0.25 -t jpeg -q 72` prend un **snapshot réel de la sortie
visible**. Une capture a lieu à l'ouverture, puis lors du changement de
workspace après 350 ms et au plus toutes les 15 s pendant que l'Overview est
fermée. Les images sont remplacées atomiquement dans
`$XDG_RUNTIME_DIR/labfy-workspace-overview/`. Le cache est éphémère et privé.
Chaque JPEG possède un manifeste JSON avec l'identité du workspace, sa sortie,
une empreinte de la hiérarchie et de la géométrie Sway, l'horodatage et le
`mtime` du fichier. `state()` ne fournit l'image que si ces données correspondent
à l'arbre courant. Les titres et le focus ne font pas partie de l'empreinte.
Une modification de taille, disposition, flottement ou composition de fenêtres
masque immédiatement l'ancien snapshot complet. Les images individuelles
disponibles restent affichées dans les nouveaux rectangles des fenêtres.
Un workspace devenu vide efface son ancienne image et son manifeste. Les
workspaces inchangés conservent leur capture.

La sortie qui porte l'Overview ne peut pas être capturée tant que sa surface
overlay est visible. Après un changement structurel, elle montre donc la
reconstruction jusqu'à la fermeture du panneau ; une capture différée de
300 ms est alors tentée. Le helper vérifie avant et après `grim` la présence
de l'overlay, l'identité et l'empreinte du workspace. Une sortie visible
différente de celle du panneau peut être recapturée pendant l'ouverture,
après 350 ms, si elle ne porte pas l'overlay. Ces captures multi-écrans n'ont
pas été vérifiées sur matériel. Une capture peut contenir une autre application
superposée à la sortie entre deux vérifications ; elle reste désignée comme
dernière capture.

`grim -T <identifiant>` capture réellement une fenêtre de cette session
SwayFX 0.6, même lorsque son workspace est caché. Le backend lit
`foreign_toplevel_identifier` sur la fenêtre dans `get_tree`, puis associe
l'image obtenue au vrai `con_id`. Passer le `con_id` à `grim -T` échoue : ce
sont deux identités distinctes. Chaque image individuelle a un manifeste
contenant les deux identifiants, son horodatage et le `mtime` du JPEG. Elle
reste utilisable après un déplacement ou un redimensionnement, et disparaît
du cache à la fermeture de la fenêtre. L'ouverture de l'Overview rafraîchit
la sortie visible et les fenêtres sans capture ; un changement structurel
recapture les fenêtres des workspaces concernés, par lots de 16 au plus.
Cette capture par toplevel n'inclut pas l'overlay de l'Overview.

La capture d'une fenêtre cachée peut refléter sa dernière frame si
l'application cesse de dessiner hors écran. `grim -T` ne fournit pas le rendu
composé d'un workspace caché. **Aucune carte n'est présentée comme live.**
Un workspace dont la capture complète est encore compatible montre ce
snapshot. Après un changement, la carte place les dernières images des
fenêtres encore présentes selon `get_tree`. Si une fenêtre n'a pas de capture
individuelle valide, son rectangle reste une reconstruction géométrique.
Les rectangles reprennent la géométrie réelle,
le focus, la position flottante et le titre de l'application. Les onglets et
les piles sont représentés par les rectangles et titres des feuilles ; leur
ornement Sway exact n'est pas reproduit.

Les sorties sont obtenues par `get_outputs`, les workspaces par
`get_workspaces`, les fenêtres par `get_tree`. Les changements `window`,
`workspace` et `output` déclenchent une relecture regroupée à 220 ms lorsque
la vue est ouverte. Chaque barre capture uniquement sa propre sortie. La
sélection du panneau passe par la sortie focalisée de Sway. Une seule sortie a
été vérifiée réellement ; les déplacements et captures entre plusieurs
sorties demandent un contrôle sur matériel multi-écrans.

La commande de déplacement valide le `con_id`, attend la réponse de Sway, puis
compare les arbres avant et après. Les numéros source et destination, ainsi que
les workspaces dont l'empreinte a changé, sont renvoyés à l'interface. Les
événements IPC provoquent aussi une relecture regroupée pour les changements
externes. La sélection clavier initiale suit le workspace réellement focalisé.
Le cache éphémère garde au plus une paire JPEG/manifeste par fenêtre encore
présente dans les workspaces 1 à 10, plus les captures complètes compatibles
des sorties ; les fichiers temporaires interrompus sont retirés après une
période de grâce. Aucun service supplémentaire n'est lancé.

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
