# Dock QuickShell, Tela et favoris partagés V1

Implémentation dans le worktree `/home/fy59/.dotfiles-worktrees/quickshell-dock-tela`,
branche `codex/quickshell-dock-tela`, base `a556cd56`. Aucun commit ni déploiement.

## Architecture et persistance

`applications/FavoritesService.qml` est le singleton du processus QuickShell.
Le menu et chaque dock lisent exactement ses `ids`, son catalogue et ses chemins
d’icônes. `ApplicationIcon.qml` est leur composant visuel commun.
Le menu conserve sa navigation clavier, sa recherche, ses catégories et son
chemin de lancement UWSM/GIO. Les handlers clavier passent explicitement avant
le traitement interne des contrôles (`Keys.BeforeItem`) pour respecter le cycle
Tab recherche → catégories → grille → recherche. Le chemin du backend est désormais relatif au module,
ce qui permet aussi de tester un worktree sans modifier la configuration active.

`~/.local/state/labfy-sway/applications-favorites.json` reste le seul stockage,
avec le même format version 1. Aucun changement de schéma. Les neuf favoris
existants ne sont ni migrés ni réordonnés au démarrage. Une liste vide existante
reste vide ; seul un fichier absent autorise le seed historique du menu.
Un favori absent du catalogue reste enregistré et apparaît dans le dock comme
indisponible, avec possibilité de le désépingler. Une réinstallation le résout
à nouveau sans changer son ordre.

Le backend Python conserve le verrou de répertoire `flock`, le fichier temporaire
privé, le remplacement atomique et les `fsync`. Les opérations ajoutées sont :

- `favorites toggle ID` : bascule atomique, y compris pour deux clics rapides
  avant réception de la première réponse.
- `favorites move ID AVANT_ID` : déplacement avant une cible encore présente.
  Une chaîne vide comme cible signifie la fin de la liste. Source ou cible
  disparue : refus sans écriture. Aucun remplacement global d’une liste périmée.
- `serve` : protocole JSON par lignes sur stdin/stdout, lecture initiale,
  mutations sérialisées et surveillance Gio du répertoire. Les remplacements
  atomiques et les écritures des anciens clients CLI sont observés.

La réponse publiée relit le stockage. Le QML ne modifie jamais les favoris par
anticipation ; un refus publie une erreur et laisse les deux interfaces sur le
même état durable. Les autres processus restent protégés par le même verrou.
Entrées bornées à 16 Kio, limite existante de 64 favoris conservée.

## Icônes

Le réglage unique est `ICON_THEME` dans `applications/shared.py`, actuellement
`Tela-circle-purple-dark`. Une instance **privée** de `Gtk.IconTheme` effectue
la résolution du `GIcon` fourni par Gio pour chaque `.desktop`, avec l’héritage
natif du thème. Les icônes absolues sont traitées comme `GFileIcon` et les URI
échappent correctement espaces et caractères spéciaux. Les icônes installées
par l’application dans hicolor/pixmaps servent de repli ; ensuite vient
`application-x-executable`. Le composant QML dessine un secours local si un
fichier est absent ou illisible, sans dépendre d’une police d’icônes.

Aucun réglage GTK/Qt global n’est écrit. Le processus utilise PyGObject/Gio déjà
employé par le backend et le typelib GTK 3 déjà présent sur cet hôte ; aucun
paquet n’a été installé. Le résolveur natif GTK évite de réimplémenter les règles
d’héritage, là où `Quickshell.iconPath` ne permet pas de choisir un thème privé.
Yazi, OrcaSlicer et AppFlowy n’ont pas d’icône correspondante dans Tela installé :
leurs icônes hicolor sont volontairement conservées. Aucun nom d’application
n’est transformé en chemin d’icône codé en dur.

## Dock et focus

Un `dock/Dock.qml` par sortie, centré et sans zone exclusive. Surface layer-shell
`Top`, namespace `labfy-sway-dock`, `WlrKeyboardFocus.None`. Les menus contextuels
sont dessinés dans cette même surface : ils n’installent aucun grab clavier.
Palette et couleurs viennent du thème Catppuccin existant. Icônes au repos à
46 px, agrandissement jusqu’à 67 px avec influence décroissante sur les voisines.
Les positions au repos servent au calcul pour éviter une boucle taille/position.
Les mouvements et le glissement vertical sont animés. Le contenu dépassement
reste défilable horizontalement avec une barre de défilement.

Machine à états pure dans `dock/AutoHide.js` : `hidden`, `arming`, `shown`,
`waiting`, `held`. Au démarrage : `hidden`. Bande sensible de 4 px, centrée,
limitée à 360 px au repos ; attente de 180 ms avant apparition, grâce de 450 ms
avant fermeture. **Un seul Timer** porte l’échéance de la machine. Pression,
glisser-déposer et menu contextuel bloquent la fermeture. Le masque d’entrée
laisse passer le pointeur hors du corps, du menu et de la bande. Les changements
de résolution recalculent la largeur disponible. Polkit et le menu d’applications
suppriment temporairement le dock via son propriétaire dans `shell.qml`.

Le bloc ajouté à `sway/.config/sway/swayfx` limite le flou au namespace du dock
et reprend `$bar_blur`. Aucun effet global supplémentaire.

## Fenêtres et actions

Un seul `swaymsg -m -t subscribe` pour les événements window/workspace/output,
possédé par le singleton. Après coupure, relance à 1,5 s et réconciliation de
l’arbre. Les rafales sont regroupées à 60 ms, et un indicateur dirty préserve
un événement survenu pendant une requête. Aucune interrogation périodique en
fonctionnement normal. Les requêtes Python utilisent directement le socket IPC,
un encodage little-endian explicite, une réponse limitée à 16 Mio et un timeout.

Correspondances par app_id, classe/instance XWayland, StartupWMClass, identifiant
desktop et exécutable. Les alias ambigus ne sont pas attribués ; aucun titre
n’est utilisé pour reconnaître une application. Les titres servent seulement
à afficher le choix entre fenêtres.

Clic gauche : lancement d’un favori installé sans fenêtre, focus explicite d’une
fenêtre, ou choix si plusieurs fenêtres. Les applications ouvertes non épinglées
suivent un séparateur. Clic droit : fenêtres, ouvrir, épingler/désépingler, fermer
le menu. Glisser un favori puis relâcher sur sa nouvelle position enregistre son
ordre. Clic molette : demande de nouvelle instance pour les terminaux dont la
politique est connue (`NEW_INSTANCE_IDS`), sans promesse pour une application
singleton inconnue.

`focus` valide le con_id dans l’arbre courant ; un scratchpad caché est montré
avant focus. Cette commande n’est appelée que par les handlers de clic. Ni la
machine à états, ni le watcher, ni les animations ne l’appellent. Les surfaces
layer-shell n’entrent pas dans l’arbre des toplevels et les snapshots Session V2.
Aucun fichier du greeter, PAM, Keyring ou moteur Session V2 n’est modifié.

## Validation reproductible

Depuis le worktree, sans arrêter la session graphique active :

```sh
python -m unittest discover -s tests/applications -v
node tests/applications/test_model.js
python -m unittest discover -s tests/dock -v
node tests/dock/test_models.js
python tests/dock/headless.py
python tests/dock/shell_load.py
python tests/dock/session_compat.py
python tests/session_v2/validate_keyring.py --sway /usr/bin/sway
git diff --check
```

Les tests graphiques créent un compositeur SwayFX headless enfant avec HOME,
XDG, socket Wayland et socket Sway privés. Le test Firefox utilise son propre
profil. `wtype` envoie Tab uniquement au compositeur privé. Le proxy de test coupe
les connexions IPC pour exercer la reconnexion réelle. Les enfants du laboratoire
sont arrêtés à la sortie. Aucun environnement ni journal Session V2 utilisateur
n’est réutilisé.

Les captures `validation/quickshell-dock-tela/{closed,open,zoom}.png` et le JSON
`result.json` proviennent de ce laboratoire. Les scénarios incluent clic droit,
choix/pinning, drag souris réel, agrandissement mesuré, entrée/sortie, ordre durable,
refus de déplacement, zéro favori après redémarrage, installation/désinstallation
d’une entrée de catalogue, client CLI externe, navigation clavier du menu,
Firefox, deux Kitty, flottant, scratchpad, fermeture et résolution.

La suite de non-régression Session V2/Keyring couvre 93 tests backend et ses
scénarios graphiques. `session_compat.py` exécute aussi les scénarios chooser et
Keyring existants avec le dock présent : prêt, acceptation, annulation, timeout,
absence, verrouillage persistant, collection différente, redémarrage pendant
l’unlock, succès/échec de restauration, nouvelle session et focus différé réel.

## Limites et intégration après revue

- Une application sans identité desktop correspondante reste visible sous son
  identité fenêtre avec une icône générique, sans épinglage inventé. Les alias
  réellement nécessaires peuvent être ajoutés après observation de l’app_id ou
  de StartupWMClass ; le titre ne doit pas devenir une heuristique.
- Yazi/Neovim hébergés dans une fenêtre Kitty ordinaire ont l’identité Kitty.
  Le dock ne déduit pas leur identité du titre ou du processus enfant. Le
  comportement de lancement terminal existant est conservé.
- XWayland est couvert par des arbres de test ; la recette graphique privée
  désactive XWayland. Une vérification avec une vraie application X11 reste utile.
- Le greeter/PAM réels ne sont pas exécutés dans la recette. La compatibilité
  Keyring et restauration est exercée avec leurs fixtures privées et les vrais
  composants de production. Un cycle de connexion matériel reste une recette
  manuelle après revue, jamais déclenchée ici.
- Les PNG ne prouvent pas à eux seuls la qualité du flou sur une fenêtre réelle ;
  la règle SwayFX est chargée dans le laboratoire. Aucun test tactile ou écran
  à facteur d’échelle fractionnaire n’est revendiqué.

La livraison reste dans le worktree. Examiner les sources, les tests, les PNG et
le patch complet adjacent au worktree. Après validation humaine, appliquer le
patch sur la base compatible dans le dépôt principal, sans copier le fichier de
favoris. Vérifier d’abord avec `git apply --check CHEMIN_DU_PATCH`, puis appliquer
selon votre procédure de revue. Recharger ensuite QuickShell et Sway pour le
nouveau module et la règle de flou. Le rechargement n’a pas été exécuté ici.

## Références des contrats de plateforme

- [QuickShell WlrLayershell](https://quickshell.org/docs/v0.3.1/types/Quickshell.Wayland/WlrLayershell/) : modes de focus layer-shell, recoupés avec les types installés de 0.3.2.
- [Spécification des thèmes d’icônes](https://specifications.freedesktop.org/icon-theme/) : résolution et héritage délégués au toolkit.
- [Protocole IPC i3/Sway](https://i3wm.org/docs/ipc.html) : framing et événements, vérifiés avec le SwayFX privé installé.
