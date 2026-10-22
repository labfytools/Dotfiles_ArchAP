# QuickShell Dock Tela — Polish V2

Livraison isolée du 22 octobre 2026, base `d4e2a001`, branche
`quickshell-dock-tela-polish-v2`, worktree
`/home/fy59/.dotfiles-worktrees/quickshell-dock-tela-polish-v2`.
La configuration du bureau actif n’a pas été modifiée ou rechargée.

## Cause et correction du hover

La V1 animait la largeur de chaque case de la `Row` et celle de chaque
`ApplicationIcon`. Chaque déplacement du pointeur modifiait donc les positions
suivantes, la largeur de la rangée et potentiellement celle de la surface.
De plus, `ApplicationIcon` calcule le `sourceSize` de son image depuis sa largeur :
la variation de taille demandait de nouvelles résolutions de rasterisation pour
les SVG Tela asynchrones. Ces deux chemins constituent les causes structurelles
identifiées des saccades et du risque de clignotement. Aucun profilage GPU du
bureau physique n’est revendiqué.

Les cases gardent désormais une largeur de 54 px (plus le séparateur éventuel),
un pas de 57 px et des cibles souris fixes. Les images restent à 46 × 46 px,
avec une résolution demandée fixe de 92 × 92 px. Seul leur `scale` varie de
1 à 1,39, ancré en bas, avec une interpolation OutCubic de 80 ms. La taille
visuelle maximale est ainsi d’environ 64 px. Les deux marges de 12 px à
l’intérieur du viewport protègent aussi les icônes agrandies aux extrémités,
y compris après défilement sur un petit écran.

L’influence du pointeur est une courbe smoothstep, symétrique, de rayon 76 px.
Ce rayon est inférieur à un pas et demi : seules la case la plus proche et ses
voisines immédiates peuvent recevoir une cible de grossissement non nulle.
Les positions de référence restent indépendantes de la transformation.
Les transitions peuvent brièvement finir leur interpolation après la sortie
du rayon. Aucun IPC, blur, chargement d’image ni relayout n’est déclenché par
l’animation elle-même. Les petits calculs d’influence restent liés au pointeur ;
aucun timer de polling ou délai de regroupement supplémentaire n’est nécessaire.

## Fond flottant

Le voile principal passe de 89 % à **16 % d’opacité**, sa hauteur de 70 à 58 px,
avec une bordure de 1 px à 9 % d’opacité. Une `RectangularShadow` QtQuick.Effects,
de géométrie fixe, produit l’ombre diffuse (blur 24, spread 2, noir à 32 %).
Elle ne capture ni les icônes ni le bureau. Le mode de contraste élevé conserve
un fond plus soutenu à 94 % et une bordure à 50 % pour la lisibilité.

La règle SwayFX du seul namespace `labfy-sway-dock` désactive le flou du fond.
Le compromis retenu est un verre teinté très transparent, sans réfraction ni
flou des fenêtres derrière. Le rendu ne dépend donc plus d’un flou compositeur
recalculé pendant le hover. Les effets de la barre restent inchangés.
`RectangularShadow` nécessite Qt ≥ 6.9 ; l’hôte testé utilise Qt 6.12.0,
QuickShell 0.3.2 et SwayFX 0.6 (Sway 1.12.0).

## Contrats préservés

La machine auto-hide conserve sa bande de 4 px, son armement de 180 ms,
sa grâce de sortie de 450 ms et son animation verticale de 210 ms.
`WlrKeyboardFocus.None`, couche Top, `exclusiveZone: 0` et le masque d’entrée
restent en place. Aucune place permanente n’est réservée à l’écran.
Le menu, `FavoritesService`, la résolution Tela et le format des favoris
partagés sont inchangés. Aucun fichier Session V2, Keyring, PAM, greetd ou
logique de session n’a été modifié.

## Validation

Les tests s’exécutent dans un Sway privé headless, avec HOME, XDG,
sockets Wayland/Sway et profil Firefox privés, sans bus de session hérité. Les enfants sont arrêtés par
le laboratoire. Les journaux et résultats sont conservés dans
[validation/quickshell-dock-tela-polish-v2](validation/quickshell-dock-tela-polish-v2/).

Commandes reproductibles depuis le worktree :

```sh
python -m unittest discover -s tests/applications -v
node tests/applications/test_model.js
python -m unittest discover -s tests/dock -v
node tests/dock/test_models.js
python -m unittest discover -s tests/session_v2 -v
python tests/dock/headless.py
python tests/dock/shell_load.py
python tests/dock/session_compat.py
python tests/session_v2/validate_keyring.py --sway /usr/bin/sway
git diff --check
```

Résultats : 7 tests applications, 6 tests dock, 93 tests Session V2 backend,
les deux suites JavaScript, le chargement du shell complet, le scénario dock
et les scénarios Session V2/Keyring avec dock passent. Le validateur Keyring
complet termine avec ses onze contrôles à zéro (succès).

Le test dock vérifie notamment :

- 73 positions latérales sans changement de géométrie, sans changement d’état
  des images et avec au plus trois influences non nulles ;
- 4,5 secondes de balayage continu, un mouvement souris par frame Qt,
  sans changement de géométrie ni d’état de chargement des images ;
- extrémités non rognées après défilement sur une sortie de 400 px ;
- auto-hide, maintien pendant le menu contextuel, drag réel et redémarrage vide ;
- synchronisation menu/dock/client externe et réordonnancement durable ;
- absence de vol de focus vers le dock, fenêtres Kitty/Firefox privées,
  reconnexion IPC et changements de résolution ;
- navigation clavier du menu et présence de la règle SwayFX sans blur du dock.

Le dernier passage mesure 281 intervalles : moyenne 16.00 ms,
95e percentile 16.46 ms, maximum 16.62 ms.
Les intervalles d’animation sont conservés dans `result.json` ; ce sont des
mesures de cadence Qt avec rendu logiciel, pas des timestamps de présentation
matérielle. Ils établissent la stabilité du laboratoire privé. La perception
sur le GPU, le fond d’écran et les sorties physiques de la session active reste
à confirmer après intégration, sans prétendre l’avoir observée ici.

Captures issues de `grim`, sans retouche :

- [Dock fermé](validation/quickshell-dock-tela-polish-v2/closed.png).
- [Dock ouvert](validation/quickshell-dock-tela-polish-v2/open.png).
- [Dock survolé](validation/quickshell-dock-tela-polish-v2/zoom.png).
- [Survol sur fond clair : ombre et transparence](validation/quickshell-dock-tela-polish-v2/zoom-light.png).

## Intégration

Le patch complet, fichiers nouveaux et PNG compris, se trouve à côté du worktree :
`/home/fy59/.dotfiles-worktrees/quickshell-dock-tela-polish-v2.patch`.
Les changements restent non commités et aucun fichier de favoris n’est livré.

Après revue, depuis le dépôt principal à la base compatible :

```sh
cd /home/fy59/.dotfiles
git apply --check /home/fy59/.dotfiles-worktrees/quickshell-dock-tela-polish-v2.patch
git apply /home/fy59/.dotfiles-worktrees/quickshell-dock-tela-polish-v2.patch
swaymsg reload
systemctl --user restart quickshell-labfy-sway.service
```

La vérification `git apply --check` est effectuée à la livraison. Les trois
commandes d’application/rechargement restent à exécuter lors de l’intégration.
Le redémarrage QuickShell recharge aussi les autres composants du shell.
Après intégration, vérifier visuellement un balayage latéral, l’auto-hide et
le menu sur les sorties physiques. Il n’est pas nécessaire de réécrire les
favoris ou de redémarrer la session utilisateur.
