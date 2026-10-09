# labfy-lock V1 — verrouillage de production

`labfy-lock` lance une configuration QuickShell distincte de `labfy-sway`.
Elle n'importe ni `shell.qml` ni `Bar.qml` et ne crée ni serveur de
notifications, ni agent Polkit, ni contrôleur d'apparence. `WlSessionLock`
demande au compositeur une surface opaque par sortie. Une seule conversation
`PamContext` est partagée par toutes les sorties. Le wrapper sérialise les
demandes avec `flock`, associe le PID à son heure de création `/proc` et à
une génération aléatoire, puis interroge **ce PID** jusqu'à `secure`. Son
retour ne signifie jamais que PAM a réussi.

## État du lot

Le processus et le wrapper sont installés par les liens Stow. Le raccourci
Sway `$mod+Alt+o`, le bouton Verrouiller du Control Center et les commandes
`timeout 300` et `before-sleep` de `swayidle.service` appellent tous
`/home/fy59/.local/bin/labfy-lock`. Les délais 300/360/420 s, l'alimentation
des sorties, la pause média et `idlehint 420` restent identiques. Le wrapper
rend la main après la confirmation `secure`, sans attendre le déverrouillage.
Le service PAM dédié `labfy-lock` est installé sous `/etc/pam.d/labfy-lock`.
Le paquet `swaylock` a été retiré après deux déverrouillages réels réussis,
dont un après sa suppression. Le fichier PAM qu'il fournissait a disparu ;
la politique dédiée reste installée.
Aucune action de veille/reprise physique n'a été testée.

La source suivie de la politique est
[`system/pam.d/labfy-lock`](../../../../system/pam.d/labfy-lock), avec sa
[procédure de réinstallation](../../../../system/pam.d/README.md). Un
déverrouillage réel avec `config: "labfy-lock"` a obtenu `PamResult.Success`,
libéré `WlSessionLock` et rendu le bureau avant et après suppression du paquet.
Le paquet `swaylock` n'est plus requis pour cette authentification.

## PAM et saisie

`PamContext` nomme explicitement le service `/etc/pam.d/labfy-lock`, qui
contient `auth include login`, comme l'ancienne politique `swaylock`.
La chaîne `login` inclut `system-local-login`, `system-login`, puis
`system-auth` pour la phase `auth`, notamment `pam_faillock` et `pam_unix`.
QuickShell 0.3.1 ne prend en charge que `auth` : cela ne démontre pas une
équivalence des phases `account` et `session` du binaire `swaylock`.
Les piles PAM globales ne sont pas modifiées.

L'utilisateur provient de l'UID effectif via `pwd.getpwuid`, sans identifiant
codé en dur. La conversation PAM démarre dès que le verrou est `secure`.
Entrée répond uniquement lorsque `responseRequired` est vrai ; si la demande
n'est pas encore prête, la saisie reste dans le champ. Le libellé et la
visibilité proviennent de PAM.
Échap vide la saisie et annule la conversation. Seul `PamResult.Success` de
la conversation non annulée, avec verrou `secure`, appelle `unlock()`.
`Failed`, `Error`, `MaxTries` et les réponses tardives ne libèrent rien.
La zone de saisie est vidée après envoi et fin de conversation. Cela ne
garantit pas l'effacement physique de toute la mémoire Qt/QML.

La disposition active vient de `swaymsg get_inputs` quand disponible.
L'état initial de Verr. maj. n'est pas exposé par cette source ; l'indication
après une pression sur la touche est indicative, pas un contrôle matériel.

## Apparence et confidentialité

Le fond provient de `labfy-appearance/effective.json`, pas d'une capture.
La palette Catppuccin effective est lue sans lancer de second contrôleur.
Une couleur opaque reste présente si le fond ou la palette manque. L'avatar
vient exclusivement d'une image PNG AccountsService validée, sinon un
pictogramme neutre. Le média MPRIS exclut `playerctld`, respecte les
capacités des boutons et ne charge que des pochettes `file://` bornées.
La progression n'est montrée que si le lecteur expose une position fiable.
Aucune action d'ouverture d'application, navigateur ou URI n'est présente.

Depuis le bureau déverrouillé :

```sh
labfy-lock-settings media hidden    # masque la carte
labfy-lock-settings media generic   # commandes, sans métadonnées
labfy-lock-settings media metadata  # titre, artiste et pochette locale
```

Le serveur de notifications de la barre publie une projection bornée dans
`$XDG_RUNTIME_DIR` : icône, nom public et compteurs, au plus quatre
lignes. Le lockscreen ne lit jamais l'historique privé. Si la barre n'a pas
encore publié ce fichier, la carte est absente. Sa présentation ne marque
aucune notification comme lue.

Le wrapper pose un garde de capture **avant** de démarrer QuickShell.
L'Overview et son backend refusent alors les captures automatiques. Le garde
reste actif après un crash ; il passe à `released` seulement après le
déverrouillage PAM. Ce fichier est une protection des captures, pas une preuve
du verrouillage Wayland. `Quickshell.watchFiles = false` désactive le
rechargement du code dans le processus verrouilleur ; les FileView de données
peuvent toujours se mettre à jour.

## Essai visuel et essai réel

La fixture autonome ne demande jamais de mot de passe ni PAM :

```sh
quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
```

Elle affiche « APERÇU — NON VERROUILLÉ » et des données synthétiques.
Elle vérifie les proportions et la suppression des cartes sur petit écran,
mais ne remplace pas un essai de la vraie surface de verrou.

Avant un essai réel, arrêter les captures et diagnostics pouvant
observer la saisie, vérifier l'accès à un TTY distinct et conserver une
session disponible pour la récupération. L'utilisateur lance localement
`labfy-lock`, saisit lui-même son secret, puis confirme le retour au bureau.
Ne jamais transmettre le secret dans un chat, un script ou un fichier.
Le déclenchement par l'IPC Sway de la commande du raccourci a été confirmé
jusqu'à l'état `secure`. Le timeout réel de 300 s, l'extinction d'écran et
la séquence d'inactivité ont ensuite été validés en usage réel.

## Récupération et retour arrière

En SwayFX headless isolé, après un `SIGKILL` du verrouilleur confirmé, une
nouvelle instance `labfy-lock` a obtenu `secure`. Cela teste une voie de
récupération pour **ce build** ; cela ne garantit pas tous les états d'une
session physique ni la conservation de l'état après une panne du compositeur.
Un crash laisse l'écran protégé par la politique du compositeur. Depuis un
TTY distinct et avec le même utilisateur, on peut tenter une nouvelle
instance en visant le socket Wayland de la session :

```sh
XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-1 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
  ~/.local/bin/labfy-lock
```

Vérifier le vrai nom du socket avant cette commande. Si un autre verrou
`WlSessionLock` est déjà présent, ne pas le tuer : le second verrou est
refusé. Aucun repli automatique vers un autre verrouilleur n'a lieu après
acquisition. Un échec du wrapper ne retarde pas indéfiniment logind ; le
délai observé est de cinq secondes.

Pour un retour arrière PAM, réinstaller d'abord le paquet avec
`sudo pacman -S swaylock`, confirmer l'existence de `/etc/pam.d/swaylock`,
remettre temporairement `config: "swaylock"` dans le seul `PamContext`,
recharger uniquement le lockscreen si nécessaire, puis refaire un essai
manuel. Ne pas exécuter ce retour arrière tant que `labfy-lock` fonctionne.

Pour revenir aussi au verrouilleur historique, restaurer dans la source suivie
`systemd/.config/systemd/user/swayidle.service` exactement
`timeout 300 'swaylock -f -c 000000'` et
`before-sleep 'playerctl -a pause 2>/dev/null || true; swaylock -f -c 000000'`.
Puis exécuter `systemctl --user daemon-reload` et redémarrer
`swayidle.service` uniquement s'il était actif avant le rollback. Restaurer
également `exec swaylock` dans `sway/.config/sway/bind` et `["swaylock"]`
pour l'action Verrouiller du Control Center, puis recharger Sway. Ne jamais
lancer `swaylock` par-dessus un `WlSessionLock` encore détenu.

## Validation isolée

QuickShell 0.3.1, SwayFX 0.6. Tests : `qmllint`, garde PAM, projection privée,
wrapper concurrent, refus d'un second `WlSessionLock`, réacquisition après crash, ajout et
retrait d'une sortie avec échelle 1,5 et redimensionnement, aperçu sur
1280×720 et 800×600. Démarrage jusqu'à `secure` : 0,209 à 0,216 s sur trois
sessions headless fraîches ; RSS 443 à 448 Mo, PSS environ 341 Mo avec
`WLR_RENDERER=gles2` logiciel. Un verrou QuickShell minimal mesure déjà
environ 308 Mo RSS et 219 Mo PSS dans cette configuration ; ces valeurs ne
prédisent pas la consommation sur le GPU physique. Le 9 octobre 2026, un
déverrouillage PAM sur la session physique `tty1` a été confirmé par l'arrêt
du verrouilleur et le passage du garde de capture à `released`. La
veille/reprise et un ensemble de sorties physiques n'ont pas été validés.

## Composition visuelle V2 (historique, remplacée par V3)

`LockContent.qml` sert à la surface verrouillée et à la fixture non verrouillée.
L'heure et la date en français sont centrées en haut ; la batterie, quand elle
existe, reste sous la date. L'avatar, l'identité, la demande PAM, la saisie,
la disposition clavier et une ligne de retour réservée forment un bloc central
stable. Les cartes média et notifications publiques sont réunies en bas,
centrées, avec au plus deux cartes de 420 px chacune. Chaque carte absente
libère sa place. Sous 900 px de largeur, elles s'empilent ; sous 850 px de
hauteur dans ce mode, elles disparaissent pour préserver le formulaire. Sous
680 px de hauteur, les cartes disparaissent également.

La fixture emploie uniquement des données synthétiques, sans fond personnel.
Les variables suivantes permettent de vérifier les états, sans PAM ni verrou :

```sh
LABFY_LOCK_PREVIEW_SCENARIO=both quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
LABFY_LOCK_PREVIEW_SCENARIO=media quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
LABFY_LOCK_PREVIEW_SCENARIO=notifications quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
LABFY_LOCK_PREVIEW_SCENARIO=none LABFY_LOCK_PREVIEW_BATTERY=absent \
  LABFY_LOCK_PREVIEW_FEEDBACK=error LABFY_LOCK_PREVIEW_CAPS=on \
  quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
LABFY_LOCK_PREVIEW_SCENARIO=long quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
LABFY_LOCK_PREVIEW_FEEDBACK=pam quickshell --path ~/.config/quickshell/labfy-lock/Preview.qml
```

Capture synthétique : `docs/assets/screenshots/quickshell-lock-style-v2-synthetic.png`.

## Composition visuelle V3

La surface et la fixture partagent désormais une seule colonne horizontale
centrée : heure, date, avatar, identité, batterie discrète, demande et champ de
saisie, zone stable pour disposition clavier/Caps Lock et retour PAM, player,
puis notifications. Les deux cartes secondaires sont immédiatement sous la
zone d'authentification et disparaissent séparément si leurs données manquent.
Elles restent sous le champ à 1280×720 et 800×600, avec une pochette plus petite
sur écran compact. Aucune carte n'est placée dans un coin.

Le mode média par défaut est désormais `metadata` pour afficher la pochette
lorsqu'elle existe. Dans ce mode, une pochette locale `file://` de 4 096 caractères
au plus est affichée à 72 px, y compris en format compact, avec titre et artiste
tronqués. Si l'URI manque ou si l'image ne se charge pas, le repli est un
pictogramme de 32 px. Les URI distantes restent exclues par la politique locale
existante. Le mode `generic` configuré par l'utilisateur
conserve sa politique de masquage des métadonnées. Seules les commandes
supportées par le lecteur sont visibles. Les notifications n'affichent que deux
applications publiques au plus, avec icône, nom et compteur ; ni résumé ni
corps privé ne sont lus ou affichés.

La fixture utilise une pochette générée pour les scénarios `both`, `media` et
`long`. `LABFY_LOCK_PREVIEW_SCENARIO=noart` montre le repli sans pochette.
`none`, `notifications`, `LABFY_LOCK_PREVIEW_FEEDBACK=error|pam|prompt` et
`LABFY_LOCK_PREVIEW_CAPS=on` couvrent les autres états synthétiques.
Le prompt PAM normal reste au-dessus du champ, sans doublon rouge sous la saisie.
Seules les erreurs PAM et d'authentification sont rouges ; une information PAM
éventuelle conserve la couleur neutre. La fixture accepte aussi
`LABFY_LOCK_PREVIEW_ART_URI` pour une copie locale synthétique à URI longue.
Capture V3 sans données personnelles :
`docs/assets/screenshots/quickshell-lock-style-v3-synthetic.png`.
