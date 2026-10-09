# Yazi comme FileChooser du portail

Package GNU Stow : `stow -d ~/.dotfiles -t ~ portal`. Les fichiers actifs dans
`~/.config/xdg-desktop-portal/` et
`~/.config/xdg-desktop-portal-termfilechooser/` sont des liens Stow. La règle
SwayFX est dans le package `sway`.

## Dépendances

Arch Linux : `xdg-desktop-portal`, `xdg-desktop-portal-gtk`,
`xdg-desktop-portal-wlr`, `kitty`, `yazi`, `jq`, `swayfx`, `libinih`,
`libsystemd`, `meson`, `ninja` et `scdoc` pour une compilation complète. Le
backend retenu est
[`hunkyburrito/xdg-desktop-portal-termfilechooser`](https://github.com/hunkyburrito/xdg-desktop-portal-termfilechooser),
version 1.4.3, commit `bcb2387949e4eb38a35390ebf1693f92869e619d` dans
l'installation testée. Le paquet AUR
`xdg-desktop-portal-termfilechooser-hunkyburrito-git` existe aussi.

Cette machine utilise une installation Meson utilisateur sous `~/.local`, sans
changer les backends système. Les fichiers nécessaires sont
`~/.local/libexec/xdg-desktop-portal-termfilechooser`,
`~/.local/share/dbus-1/services/org.freedesktop.impl.portal.desktop.termfilechooser.service`
et `~/.local/share/xdg-desktop-portal/portals/termfilechooser.portal`.
La procédure de reproduction, conservée dans ce dépôt indépendamment du cache
de construction, est la suivante (sans l'exécuter pendant une simple publication) :

```sh
git clone https://github.com/hunkyburrito/xdg-desktop-portal-termfilechooser.git
cd xdg-desktop-portal-termfilechooser
git checkout --detach bcb2387949e4eb38a35390ebf1693f92869e619d
meson setup build --prefix="$HOME/.local"
meson compile -C build
meson install -C build
```

Contrôler ensuite les trois chemins ci-dessus et la configuration Stow de ce
dossier. Le dépôt source et le répertoire `build` sont temporaires et ne font
pas partie des dotfiles. Cette procédure installe uniquement dans le préfixe
utilisateur ; elle ne remplace aucun paquet système.
Après installation ou mise à jour du backend, recharger seulement
`xdg-desktop-portal.service` après avoir vérifié qu'aucune session de partage
d'écran ou requête portal n'est en cours.

## Routage et fenêtre

`FileChooser` utilise `termfilechooser`, `ScreenCast` et `Screenshot` utilisent
`wlr`, `Secret` utilise `gnome-keyring`, et les autres interfaces disponibles
gardent `gtk`. `XDG_CURRENT_DESKTOP=sway:wlroots:swayfx` sélectionne la
configuration utilisateur `portals.conf` avant les fichiers système propres à
Sway. Le wrapper lance Kitty avec `--class labfy-yazi-filechooser` ; SwayFX
flotte et centre uniquement cet `app_id`. Kitty calcule au lancement une taille
de 1000 × 650, bornée à la sortie SwayFX active avec une marge de 40 pixels.
La fenêtre reste redimensionnable et sur le workspace courant. Le thème Kitty
et le thème Yazi Catppuccin Mocha sont ceux de la configuration habituelle.

Firefox 157 utilise le portail FileChooser en mode automatique quand il est
disponible. Aucun `GTK_USE_PORTAL` global ni préférence de profil n'est
nécessaire dans cette installation. Pour diagnostiquer un profil différent,
vérifier `widget.use-xdg-desktop-portal.file-picker` dans `about:config` : `1`
force le portail, `0` le désactive, `2` suit le mode automatique.

## Utilisation

Dans le sélecteur, `o` ou `Entrée` valide le ou les fichiers survolés ou
sélectionnés. `Espace` sélectionne chaque fichier en mode multiple. `q` annule
un choix de fichier ; `Q` annule aussi et ne transmet pas le dossier courant.
Pour un dossier, entrer dedans puis appuyer sur `q` ; `Q` annule. `M` ouvre le
menu des supports, `g` puis `Espace` permet de saisir un chemin. Ouvrir un
fichier via Yazi sans mode chooser n'est pas la même opération : ici, le
wrapper utilise `--chooser-file` pour remettre les chemins à l'application.

Pour « Enregistrer sous », le backend crée un fichier provisoire annoté. Le
déplacer avec `x`, naviguer vers la destination, le déposer avec `p`, puis le
renommer avec `r` si nécessaire. Valider le fichier avec `o` ou `Entrée`, puis
répondre `o` au prompt de confirmation du wrapper. Le prompt avertit que
l'application peut écraser une destination existante ; répondre autrement
annule. `Q` dans Yazi annule également et le backend supprime le provisoire
resté à son emplacement d'origine. Si le provisoire a été déplacé avant une
annulation, supprimer manuellement ce fichier déplacé. Les essais doivent
utiliser un dossier temporaire et éviter tout écrasement de données réelles.

Les applications GTK/Qt qui utilisent leurs dialogues natifs plutôt que le
portail conservent leur comportement. Ce réglage ne change aucune association
MIME et ne remplace pas les portails d'autres interfaces.

## Vidéo Firefox et inhibition de l'inactivité (diagnostic du 9 octobre 2026)

Lors de ce diagnostic, `swayidle.service` lançait `swaylock` après 300 s,
éteint les sorties après 360 s et met les lecteurs en pause après 420 s. Le
verrouillage manuel et la protection `before-sleep` sont indépendants. Le
symptôme historique n'a pas été observé à l'instant exact du verrouillage ;
la configuration et les mesures courtes ci-dessous identifient la chaîne
d'inactivité en cause, sans attribuer rétroactivement chaque verrouillage à
`swayidle`.

La tasse « Maintenir éveillé » de QuickShell est une demande manuelle distincte.
Elle utilise un `IdleInhibitor` sur la barre persistante, qui survit à la
fermeture du Control Center. Dans le test, l'observateur `swayidle` à 6 s ne
s'est pas déclenché pendant que l'utilisateur confirmait la tasse activée ;
après sa désactivation, il s'est déclenché à 6 s sans vidéo. Lors d'une seconde
activation, le marqueur est resté absent avec le Control Center fermé, puis
avec une fenêtre Firefox de test sans vidéo en plein écran. Ce résultat
confirme l'effet de l'inhibition manuelle en fenêtre normale et en plein écran.
Après la seconde désactivation, l'observateur a de nouveau déclenché à 6 s.
L'expiration des durées n'a pas été mesurée ici. La tasse ne doit pas servir de
substitut à la demande propre à Firefox.

Avec Firefox 157.0.1 natif Wayland, une vidéo locale avec image et son produit
une demande `video-playing` vers `org.freedesktop.portal.Inhibit`. Le portail
actif sélectionne GTK par `default=gtk`, lequel reçoit la demande via
`org.freedesktop.impl.portal.Inhibit`. GTK répond à Firefox avec un chemin de
requête, mais son relais vers `org.freedesktop.ScreenSaver` échoue : le journal
du backend indique explicitement l'absence de propriétaire de ce nom D-Bus.
Le code GTK 1.15.3 répond avant de connaître le résultat de ce relais. Une
réponse D-Bus réussie de Firefox ne prouve donc pas que `swayidle` est inhibé.
Avec la tasse désactivée, l'observateur à 6 s s'est déclenché pendant cette
lecture par le portail, comme sans lecture. Les demandes de Firefox sont
libérées à la pause et à la fermeture du média ; l'audio peut conserver son
inhibition environ 10 s après la pause.

Le protocole Wayland natif existe dans SwayFX. Un Firefox de test lancé avec
`MOZ_WAKE_LOCK_TYPE=WaylandIdleInhibit` l'a acquis en lecture avec Firefox
focalisé, en fenêtre normale, en plein écran et après passage du focus au
terminal. Dans ces mesures courtes, l'observateur à 6 s n'a pas déclenché. Ce
mécanisme ne couvre toutefois pas la reprise après pause avec le terminal
focalisé : Firefox 157 tente une nouvelle acquisition, mais ne rapporte pas de
réussite.
Dans l'essai à pause longue, l'observateur a déclenché environ 17 s après la
pause (délai audio puis délai de 6 s), et est resté en état d'inactivité après
la reprise.
Une entrée `org.freedesktop.impl.portal.Inhibit=none` supprimerait le relais
GTK défaillant, sans créer d'inhibition. Elle n'est pas installée tant que
ce cas sans focus échoue ; aucun portail n'a été redémarré et les routes
`FileChooser=termfilechooser`, `ScreenCast=wlr`, `Screenshot=wlr`, `Secret` et
les autres interfaces GTK sont conservées.

Le pont utilisateur décrit ci-dessous fournit désormais le destinataire
`org.freedesktop.ScreenSaver` manquant. La règle `Inhibit=none` n'est pas
installée et aucun portail ni `swayidle` n'a été redémarré.

## Pont ScreenSaver vers QuickShell (9 octobre 2026)

Firefox demande `org.freedesktop.portal.Inhibit`, le backend GTK relaie vers
`org.freedesktop.ScreenSaver.Inhibit`, puis
`labfy-idle-bridge.service` transmet le nombre de demandes valides à
QuickShell. L'`IdleInhibitor` de la barre persistante est actif si le maintien
manuel **ou** au moins une demande applicative est actif. La tasse reste
visible sans fond dans la barre : elle est rouge dès qu'une de ces sources est
active, et neutre sinon. Son infobulle distingue les sources et la durée
manuelle restante lorsqu'elle existe. Les deux sources
restent indépendantes : désactiver ou laisser expirer la tasse ne libère pas
une vidéo encore demandée ; une pause vidéo ne change ni la durée ni le
minuteur manuels. La petite indication dans la sous-page Maintenir éveillé
signale une demande applicative sans lui attribuer une identité non vérifiée.

Le helper Python 3 utilise PyGObject/Gio déjà installé, exclusivement sur le
bus de session. Il expose seulement `Inhibit(ss) -> u` et `UnInhibit(u)` sur
`/org/freedesktop/ScreenSaver`, avec introspection. Chaque appel reçoit un
cookie non nul propre à la connexion D-Bus appelante. La libération vérifie
ce propriétaire ; sa disparition libère toutes ses demandes. En pratique,
GTK est ce propriétaire direct : la fermeture du navigateur d'origine dépend
de la fermeture des requêtes portal par GTK. Les tests réels ont observé
`UnInhibit` après pause, fermeture du média et arrêt du navigateur de test.
Le pont ne déduit aucune vidéo d'un titre, d'un flux audio ou de MPRIS.

Mesure avec Firefox de test Wayland, profil et vidéo locale isolés, tasse
désactivée : l'observateur `swayidle` configuré avec un fichier vide et un
marqueur à 6 s déclenche sans lecture. En lecture, il ne déclenche ni en
fenêtre normale avec le terminal focalisé, ni en plein écran. Après deux
pauses longues, il déclenche quand les demandes vidéo et audio sont libérées ;
la reprise sans redonner le focus à Firefox le désactive à nouveau. À la
fermeture du média ou du navigateur de test, il déclenche à nouveau après la
libération des demandes. La demande audio est restée environ 10 s après la
pause dans ces essais, avant le délai de 6 s de l'observateur. Une tasse
manuelle active a maintenu la protection pendant une pause ; sa désactivation
pendant la lecture reprise n'a pas supprimé la protection applicative.
L'expiration réelle d'une durée manuelle et Netflix au délai habituel de 300 s
restent à vérifier séparément. Les demandes applicatives peuvent provenir
d'autres usages que d'une vidéo visible : le pont suit le portail, il ne
classe pas le contenu de la fenêtre.

Contrôle ciblé du 9 octobre 2026 : une activation manuelle de 30 minutes,
Control Center fermé, a conservé la tasse et la surface de barre pendant
130 secondes. Un observateur `swayidle` temporaire avec configuration vide,
seul un marqueur privé à 8 s et aucune action de verrouillage ou d'extinction,
ne s'est pas déclenché. Le même contrôle de 130 secondes en mode « Jusqu'à
désactivation », avec un nouveau marqueur, a donné le même résultat. Les
relevés à 0, 30, 55, 65, 90 et 130 secondes ont conservé le PID QuickShell
2349 et un seul chargement de configuration. La sous-page confirmait le mode
illimité après la seconde mesure. Ces contrôles établissent le fonctionnement
au-delà d'une minute dans la session stable ; ils ne mesurent ni l'expiration
complète à 30 minutes ni une demande applicative concurrente durant ces deux
phases. Après désactivation manuelle, un contrôle négatif neuf à 6 s a fini
par déclencher son marqueur ; les marqueurs des phases actives n'étaient donc
pas simplement inopérants.

Le journal utilisateur de la session précédente montre des rechargements
QuickShell à 08:01:31 et 08:02:15 sous le même PID 14333. Les fichiers
`WorkspaceOverview.qml` et `Bar.qml` portent des modifications à ces secondes.
À cette date, un rechargement reconstruisait `ShellRoot` avec le maintien
manuel initialisé à `false` ; il pouvait donc retirer la protection même si
le PID ne changeait pas. Faute d'horodatage du constat initial, ce lien restait
une explication plausible, sans attribution prouvée. La correction V5
ci-dessous conserve désormais ce choix lors des rechargements QML ; un arrêt
complet du processus reste distinct et libère l'inhibition.

Un rechargement ultérieur, pendant la mise à jour de la tasse, a révélé un
second défaut distinct : le nouveau `SocketServer` ouvrait le chemin fixe
avant la destruction de l'ancien. L'ancien retirait ensuite ce chemin ; le
helper ne pouvait plus se reconnecter et répondait `bridge unavailable or
full` aux nouvelles demandes. `IdleBridgeReceiver.qml` diffère maintenant
l'ouverture de la socket de 250 ms après le chargement QML. Une demande
applicative temporaire a été acquise puis libérée avec succès ; la tasse est
devenue rouge pendant la demande, et un observateur neuf à 6 s n'a déclenché
qu'après sa libération. Le même résultat a été vérifié avec un rechargement
pendant que la demande restait active : chemin de socket présent, demande
retransmise, tasse rouge et inhibition effective. Ce défaut concernait la
reconnexion automatique, pas l'échéance du minuteur manuel.

Après ces changements QML, deux nouveaux contrôles réels de 130 secondes
ont été effectués, l'un à 30 minutes et l'autre en mode illimité. À chacun
des relevés 0, 30, 55, 65, 90 et 130 s, la tasse est restée rouge, la surface
de barre était présente, le PID 2349 et le nombre de chargements étaient
stables, et un observateur à 8 s avec marqueur neuf n'avait pas déclenché.
Enfin, une demande D-Bus temporaire acquise puis libérée pendant le mode
manuel illimité n'a ni masqué la tasse ni libéré l'inhibition manuelle. Après
désactivation du mode illimité de test, la tasse est redevenue neutre et un
dernier observateur à 6 s a déclenché son marqueur privé. L'état manuel a
ainsi été ramené à sa valeur initiale.

## Maintien manuel après rechargement QML (contrôle V5, 9 octobre 2026)

Le signalement situait un nouveau verrouillage vers 13:36–13:40, sans heure
exacte. Le processus QuickShell 2349, lancé à 09:23:01, avait rechargé sa
configuration pour la dernière fois à 13:24:37 avant ce signalement.
`swayidle.service` utilisait toujours 300 s pour `swaylock`, 360 s pour
l'extinction, 420 s pour la pause média et `before-sleep` pour le verrouillage
avant suspension. Aucun fichier de configuration implicite de `swayidle`
n'était présent. Le journal contient deux succès `swaymsg` sous l'identifiant
`swayidle` à 13:36:40 et 13:38:41, compatibles avec l'extinction et la reprise
de sortie. Il ne consignait ni la sélection manuelle, ni l'état de
l'inhibiteur au moment du verrouillage : la chaîne précise de cet incident
reste donc non prouvée. L'état observé après déverrouillage n'a pas été traité
comme une mesure rétroactive.

Le code actif avant V5 plaçait le booléen manuel dans `ShellRoot` avec la
valeur initiale `false`. V5 utilise `PersistentProperties` avec une identité
stable pour conserver seulement l'activation, la durée choisie et l'échéance
absolue. Une expiration pendant un rechargement est effacée au chargement.
Les demandes applicatives restent resynchronisées depuis le pont, sans
partager le stockage manuel. Les deux rechargements réels à 14:00:34 et
14:01:09 ont restauré le mode illimité sous le même PID. Lors du second,
le nouvel hôte de l'inhibiteur était mappé et `enabled=true` avant la
destruction journalisée de l'ancien hôte, environ 24 ms après. Il n'existe
pas d'accusé d'inhibition du compositeur ; ces transitions décrivent le
cycle QML, et l'observation `swayidle` ci-dessous teste son effet réel.

Le mode illimité a été activé depuis le bouton à 13:47:51, panneau fermé.
Un observateur `swayidle` sur `wayland-1` et `seat0`, avec fichier de
configuration vide, respect normal des inhibiteurs et seule action de
création d'un marqueur privé à 8 s, n'a pas déclenché entre 13:48:55 et
13:59:17, soit 10 min 22 s sans rechargement. Un nouvel observateur de même
type n'a pas déclenché entre 13:59:34 et 14:11:28 ; son dernier rechargement
réel était à 14:01:09, soit 10 min 19 s avant la fin de la mesure. Aucun
`swaylock` n'était présent lors des relevés. Ces mesures dépassent 300 et
360 s dans la session réelle ; elles ne transforment pas l'icône seule en
preuve de protection. L'observateur ne sait pas mesurer les entrées humaines :
la confirmation de leur absence pendant ces fenêtres reste à obtenir.

Le contrôle de libération volontaire du mode manuel reste à terminer. À
14:19:36, le diagnostic indiquait encore `manual: true` et zéro demande
applicative ; aucun marqueur négatif n'avait donc pu être obtenu. Les deux
observateurs temporaires ont été arrêtés sans modifier `swayidle.service`.

Le mécanisme `PersistentProperties` ne sauvegarde rien après l'arrêt ou le
crash du processus QuickShell ; une nouvelle session repart désactivée. Une
échéance limitée est exprimée en temps civil, afin de survivre au
rechargement : un changement manuel de l'horloge système peut donc modifier
la durée effective. Le premier chargement de V5 depuis l'ancien code ne
pouvait pas récupérer le booléen non conservé ; le mode a été réactivé
volontairement pour les mesures ci-dessus. Le verrouillage manuel et celui
avant suspension restent indépendants.

Le helper envoie un état complet puis des mises à jour ordonnées sur la socket
privée du répertoire `XDG_RUNTIME_DIR`. QuickShell confirme la prise en compte
de chaque état ; cette confirmation n'est pas un accusé du compositeur. Une
déconnexion efface immédiatement la contribution applicative dans QuickShell.
À la reconnexion, le helper renvoie seulement ses demandes encore valides.
Un redémarrage du helper perd ses demandes en mémoire : les applications
doivent renouveler leur requête ; il peut y avoir une interruption temporaire
de protection. Le compteur de cookies seul est conservé dans le répertoire
runtime de la session afin qu'un ancien cookie ne désactive pas une nouvelle
demande après ce redémarrage. Aucun nom d'application, motif ou état de
demande n'est stocké sur disque ni journalisé. Le pont limite les demandes à
256 et les libellés reçus à 512 octets chacun.

Le service utilisateur est voulu par `wayland-session@sway.desktop.target`,
après le service QuickShell. Il acquiert le nom D-Bus sans remplacer un autre
propriétaire et échoue proprement en cas de conflit. GTK utilise
`DO_NOT_AUTO_START` pour ce destinataire : un fichier d'activation D-Bus seul
ne suffirait pas. Le processus reste événementiel, avec une limite mémoire
systemd de 96 Mio. Pour diagnostiquer :

```sh
systemctl --user status labfy-idle-bridge.service
busctl --user introspect org.freedesktop.ScreenSaver /org/freedesktop/ScreenSaver
python ~/.dotfiles/tests/test_idle_bridge.py
```

Pour désactiver le pont, arrêter et désactiver uniquement
`labfy-idle-bridge.service`, puis retirer son lien Stow de
`wayland-session@sway.desktop.target.wants` lors du retour arrière. Le mode
manuel QuickShell reste disponible. Aucun changement de `portals.conf`, de
backend, de `swayidle`, du verrouillage manuel ou de la protection avant
suspension n'est nécessaire. Sans ce pont, le défaut du relais GTK décrit
ci-dessus réapparaît tant qu'aucun autre service ScreenSaver fonctionnel ne
prend le relais.
