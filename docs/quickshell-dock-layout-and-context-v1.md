# QuickShell Dock — organisation et menu contextuel (11 novembre 2026)

## Objectif

Conserver le dock QuickShell SwayFX existant (zoom fixe, centrage, bande
d'activation de 4 px sur toute la largeur, couche Top sans focus clavier),
mais permettre de réorganiser les icônes épinglées et de gérer des séparateurs.

## Organisation du dock

- Glisser une icône épinglée pour la replacer par rapport aux autres favoris.
- Clic droit sur une icône épinglée : « Déplacer à gauche » et
  « Déplacer à droite » lorsqu'un déplacement est possible.
- Clic droit sur une icône épinglée : « Ajouter séparateur avant/après ».
- Cliquer ou faire clic droit sur un séparateur : déplacer à gauche/droite
  ou le supprimer. Le glisser-déposer d'un séparateur est également pris en charge.
- Les fenêtres ouvertes non épinglées demeurent après les favoris ; le
  séparateur automatique à cette frontière est conservé.

La liste partagée des favoris conserve son contrat et son fichier **v1** :
`~/.local/state/labfy-sway/applications-favorites.json`. Les séparateurs
sont enregistrés séparément dans
`~/.local/state/labfy-sway/dock-separators.json`. Le format est strict,
limité à 16 séparateurs, avec écriture atomique, verrou de répertoire et
rejet sans écrasement d'un fichier invalide. Aucun identifiant de séparateur
n'est accepté comme application exécutable.

## Fermeture et transparence du menu

Le menu contextuel n'a plus de ligne « Fermer le menu ».

- Un clic dans la marge autour du menu le ferme immédiatement, sans lancer
  l'application située derrière cette marge.
- Un éloignement du pointeur au-delà de cette zone déclenche une fermeture
  avec **480 ms de tolérance** ; survoler de nouveau le menu annule l'échéance.
- La surface Wayland d'entrée est limitée à une petite zone autour du menu et
  au dock existant. Le reste du bureau demeure interactif ; en dehors de la
  zone de capture, la fermeture provient de l'éloignement du pointeur, pas
  d'une interception globale des clics.
- Le fond de menu a **85 % d'opacité** (soit 15 % de transparence), avec les
  textes entièrement opaques. Le mode de contraste élevé conserve un fond
  presque opaque (94 %). Les survols de ses actions restent translucides.

L'auto-hide, les menus, l'animation et le focus des fenêtres ne sont pas
transformés en commandes Sway. Aucun redémarrage de Sway n'est nécessaire.

## Vérifications non destructives

- `tests/dock/test_separators.py` valide stockage, suppression, déplacements,
  corruption, liens symboliques, opérations concurrentes et invariants v1.
- `tests/dock/test_models.js` valide les séparateurs et déplacements.
- `tests/dock/headless.py` utilise un **SwayFX privé** ; les actions réelles
  du menu sont exercées, y compris clic à côté, délai d'éloignement, survol
  prolongé, couleur et gestion réelle d'un séparateur.
- Les tests applications/dock, le shell complet, la compatibilité Session V2
  et le lint QML sont exécutés avant l'activation sur ArchASP.

Les traces de test sont conservées dans
`~/.cache/labfy-dock-context-dismiss-v1`. Aucune modification volontaire
de la liste réelle de favoris ni de l'état Session Restore V2.

## Correction de la zone morte centrale (11 novembre 2026)

La fermeture automatique introduisait une régression dans la zone de survol :
les régions `dismissZone` et `context` étaient **soustraites** du masque
Wayland lorsqu'elles étaient invisibles. Leur géométrie continuait pourtant
d'exister, ce qui creusait des trous dans la bande sensible de 4 px, notamment
au centre de l'écran.

Les régions secondaires du masque utilisent désormais uniquement l'opération
`Combine`, avec largeur et hauteur égales à zéro tant que leurs composants
ne doivent pas recevoir la souris. Le capteur pleine largeur n'est donc
jamais soustrait, ni au démarrage ni après fermeture d'un menu. La zone
cliquable du menu n'est ajoutée qu'à son ouverture.

Le test SwayFX privé `tests/dock/headless.py` vérifie les trois régions
vides lorsque le dock est masqué, leur activation lorsque le menu apparaît,
leur désactivation après fermeture et un nouveau survol au centre, en plus
des deux coins. Il n'agit pas sur le pointeur physique de l'utilisateur.
