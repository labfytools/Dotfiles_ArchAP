# QuickShell labfy-sway

Le [moteur de thème commun](theme/README.md) fournit les couleurs effectives
à QuickShell et Sway/SwayFX depuis une seule palette Catppuccin versionnée.

Barre principale et serveur de notifications de la session SwayFX.

Le haut-parleur de la barre ouvre le [mixeur audio du Control Center](controlcenter/AUDIO_MIXER.md),
avec sorties, flux de lecture et microphones. Le volume général conserve son
contrôleur partagé avec la barre et ses pas de 1 point au défilement.

Le bouton Arch **Applications**, premier élément à gauche même en mode Resize,
ouvre le [menu d'applications](applications/README.md) sous la barre.
`Mod+Alt+L` ouvre ce menu sur la sortie focalisée.

```text
Bar
├── Applications
├── Workspaces
├── Workspace Overview
├── Window/task switcher
├── Date Center
│   ├── MPRIS
│   └── Notifications
├── Right Status
│   ├── Network
│   ├── Bluetooth
│   ├── Battery
│   ├── Maintenir éveillé (si actif)
│   ├── Updates
│   ├── Supports amovibles
│   ├── Presse-papiers
│   ├── Tray
│   └── Control Center
└── Control Center
    ├── Wi-Fi
    ├── Bluetooth
    ├── Volume
    ├── Brightness
    ├── Power Profile
    ├── Maintenir éveillé
    ├── Apparence
    │   └── Fond d'écran
    ├── Battery limit
    └── Session
```

Dans **Réglages rapides → Maintenir éveillé**, sélectionner 30 minutes,
1 heure, 2 heures ou **Jusqu’à désactivation**. L’icône de la barre apparaît
pendant l’inhibition ; son infobulle indique le temps restant et un clic rouvre
la page pour changer la durée ou désactiver le mode. Une seule barre porte
l’inhibiteur Wayland, même avec plusieurs écrans. Le mode empêche l’inactivité
détectée par le compositeur, donc les actions automatiques de `swayidle`
(verrouillage et extinction de l’écran) tant que l’inhibition est respectée.
Il ne bloque pas le verrouillage manuel, la veille demandée explicitement ni
le verrouillage avant mise en veille. L’état est propre au processus
QuickShell : son arrêt ou redémarrage libère l’inhibition. La configuration et
le cycle de vie de `swayidle.service` ne sont pas modifiés.

Les demandes automatiques des applications arrivent séparément par le pont
`org.freedesktop.ScreenSaver` décrit dans [portal/README.md](../../../../portal/README.md).
Le même inhibiteur de la barre reste actif tant que la tasse manuelle ou au
moins une demande applicative valide est présente. La sous-page indique une
demande automatique sans changer la durée de la tasse ; désactiver la tasse
ne retire pas la demande d'une vidéo encore en lecture. La disparition du
helper efface sa seule contribution applicative, tandis que la tasse garde
son propre état.

L'icône **Presse-papiers** ouvre le panneau d'historique sous la zone droite de
la barre ; `Mod+Alt+V` conserve le même basculement sur l'écran focalisé.
L'architecture, les raccourcis, les tests isolés et le retour vers Wofi sont
décrits dans [clipboard/README.md](clipboard/README.md).

`Super+W` ouvre la [vue d'ensemble visuelle](overview/README.md) sur la sortie
focalisée. `Super+Shift+W` conserve le layout Sway `tabbed`.

`quickshell-labfy-sway.service` est activé par
`wayland-session@sway.desktop.target`, sans autostart Sway parallèle.
`NotificationService.qml` possède `org.freedesktop.Notifications` ; l'historique
est écrit hors Git via `Quickshell.statePath("notifications.json")` dans
`~/.local/state/quickshell/`. Mako demeure installé, inactif et masqué ; voir
[ROLLBACK.md](notifications/ROLLBACK.md).

`labfy-quickshell-updates.timer` exécute `bin/check-updates.py`, qui publie un
état JSON dans `$XDG_RUNTIME_DIR`. `batlimit` (CLI) et Réglages rapides →
Batterie (GUI) passent par `/usr/local/sbin/batlimit-set`. Le seuil courant
est 60 % ; le helper root est documenté dans `bin/root/README.md`.

Dépendances essentielles : `quickshell`, SwayFX 0.6, `scenefx`, une Nerd Font,
NetworkManager, BlueZ, PipeWire, TLP/`tlpctl`, `checkupdates`, `yay`, `df`,
`python3`, `swaylock` et le helper batterie pour le réglage du seuil. Le
backlight utilise le noeud machine `amdgpu_bl1` dans `BrightnessSlider.qml`.
Les scans Wi-Fi et Bluetooth
ne sont possédés que par les pages ouvertes.

Le gestionnaire de fonds d'écran local est décrit dans
[WALLPAPER.md](controlcenter/WALLPAPER.md). Il utilise Sway et `swaybg`, sans
service permanent ni changement automatique du thème.

## Supports amovibles

`RemovableMediaIndicator.qml` affiche dans la zone d'état un indicateur
lorsqu'au moins un support éligible est présent. Son `PopupWindow` natif liste
les volumes, leur état et les erreurs publiées, puis offre les actions
**Ouvrir**, **Monter** ou **Démonter**, et **Retirer en sécurité** lorsque le
contrat le permet. Ouvrir lance Yazi dans Kitty via UWSM en utilisant le
véritable point de montage UDisks pour USB/SD ou le chemin du `GMount` pour
MTP. Le popup participe à la même exclusion mutuelle que le Date Center, le
menu des fenêtres et le Control Center.

QuickShell lit exclusivement le snapshot JSON V2
`$XDG_RUNTIME_DIR/labfy-removable-media.json`. Il refuse intégralement un
snapshot dont `schema` n'est pas `labfy.removable-media`, dont `version` n'est
pas `2`, ou dont les appareils ne respectent pas le contrat attendu. Le schéma
publie `kind` et `actions`. Chaque appareil publie aussi
`safe_remove_runtime_id`, y compris lorsque `safe-remove` n'est pas disponible.
Les identifiants MTP restent opaques et aucune URI MTP n'est publiée. Le chemin
de montage exact fourni par GVFS peut néanmoins contenir un identifiant de
l'appareil ; le snapshot est privé (`0600`). Les commandes passent sans shell à `labfy-removable-mediactl`, qui est
l'unique frontière de commande vers le daemon ; le socket Unix associé est
privé (`0600`).

Le service utilisateur est unique : il utilise l'ObjectManager UDisks pour les
systèmes de fichiers USB ou SD/MMC et `Gio.VolumeMonitor`/GVFS-MTP pour les
téléphones. Les blocs UDisks marqués `HintIgnore` ou `HintSystem` sont exclus.
Un volume `crypto_LUKS` n'est ni présenté ni déverrouillé automatiquement.
Pendant la vie du daemon, chaque support présent peut être monté
automatiquement une seule fois ; après un démontage manuel, il reste démonté
jusqu'à sa disparition puis sa réinsertion. Au démarrage ou au redémarrage, le
cold-start V1 effectue un nouveau scan : un téléphone déjà présent peut alors
être monté. Pour USB/SD, le retrait en sécurité agit au niveau du lecteur et
vérifie que ses systèmes de fichiers sont démontés avant l'éjection ou la mise
hors tension. Pour MTP, il ferme logiquement le montage GVFS sans appeler
`PowerOff`.

Le contrôle visuel synthétique peut être activé avec
`LABFY_REMOVABLE_MEDIA_TEST_STATE` (`0`, `USB`, `MTP`, `USB+MTP`, `busy` ou
`error`) dans le processus QuickShell. Ces états ne lancent aucune commande.
Les tests Python synthétiques du daemon et de son IPC sont décrits dans
[systemd.md](../../../../docs/systemd.md#supports-amovibles-usbsd-et-mtp).

Cette fonction est indépendante de Session Restore : elle ne lit ni n'écrit de
checkpoint de session et n'intervient pas dans son démarrage.

Les 29 tests `unittest` synthétiques et `qmllint` sont passants. Un Samsung réel
a été reconnu et les opérations ciblées de montage et de retrait en sécurité
ont été vérifiées dans le code isolé. La recette UI sur matériel MTP reste à
effectuer. La validation matérielle USB Ventoy V1 avait été effectuée avant le
commit précédent.

## Défilement sur les icônes et mode Resize

Les deux indicateurs du groupe système à droite de la barre règlent séparément le volume et la
luminosité par défilement vertical à deux doigts ou avec une molette. Un pas
vaut **un point de pourcentage**. Le geste physique vers le haut augmente la
valeur. Le clic sur le bouton Réglages rapides conserve son rôle.

`WheelHandler` accepte explicitement `Mouse` et `TouchPad`, et ne traite que
les 66 px de chaque zone « icône + pourcentage ». Pour un événement, `pixelDelta.y` est choisi s'il
est non nul, sinon `angleDelta.y` ; les deux ne sont jamais additionnés. Les
seuils initiaux sont **32 pixels** pour le touchpad et **120 unités angulaires**
pour un cran de molette. Le reliquat est conservé entre événements, remis à
zéro à la fin du geste si Qt fournit `ScrollEnd`, au changement de direction
ou au changement de source. Aucun délai ne jette les petits mouvements.
`LABFY_SCROLL_DEBUG=1` permet de diagnostiquer les deltas et phases reçus.

### Contrôles de barre

Le retour matériel a établi que le geste vers le haut agissait à l'envers sur
le volume. `ScrollSteps.js` applique la correction de signe **une seule fois**
aux événements de touchpad. La molette classique garde son sens et son seuil
de 120 unités. Les événements à `pixelDelta` non nul, ceux dont le périphérique
Qt est `TouchPad` et les petits deltas angulaires continus sont traités comme
gestes tactiles.

La luminosité pouvait rester bloquée après la première écriture : `onSaved`
plaçait la file en attente d'un nouveau `onLoaded` qui n'arrivait pas dans le
cas reproduit. Le watcher `FileView` peut charger la valeur avant `onSaved` ;
attendre ensuite un autre chargement n'est pas fiable. La variable
`awaitingReadback` restait alors vraie ; les demandes suivantes étaient
accumulées sans nouvelle écriture. Le diagnostic a reproduit ce cas avec le
Control Center fermé : le composant recevait `−1`, tandis que sysfs restait à
376000/400000. La correction libère la file depuis `saved`, relit la valeur matérielle
après le callback `FileView`, puis lance la dernière consigne en attente. La
relecture de ce petit fichier sysfs est bornée ; `saveFailed`, `loadFailed` et
les données invalides sont signalés. Aucun pourcentage optimiste n'est affiché.

La présentation reprend celle des indicateurs Wi-Fi, Bluetooth et batterie :
icône Nerd Font, pourcentage réel à largeur fixe, fond transparent hors survol
et infobulle. Le soleil `󰖨` remplace le glyphe ambigu ``. La disposition
finale, avec le tray tout à droite, est décrite ci-dessous.

Validation des contrôles : tests unitaires de `ScrollSteps`, `qmllint` et injection
synthétique dans `ScrollIcon.applyWheel` via un IPC temporaire retiré après
essai. Avec le Control Center fermé, le volume a fait 67 → 68 → 67 % ; la
luminosité a fait 372000 → 376000 → 372000 sur 400000, puis trois pas
rapprochés 93 → 96 % → 93 %. L'essai panneau ouvert puis refermé a conservé
la synchronisation à 93 %. L'appel direct au contrôle a également fonctionné
panneau fermé. L'injection était synthétique ; les essais tactiles et visuels
de la série ont été validés séparément et ne sont pas rejoués pour cette
publication.
Les bornes 0/100 % pour le volume et 10/100 % pour la luminosité sont testées
avec `node tests/quickshell/test_percent_math.js`, sans pousser le matériel
aux extrêmes.

Le volume utilise `Pipewire.defaultAudioSink` et son `PwObjectTracker`, comme
le curseur du Control Center. Il est borné entre 0 et 100 %, sans changer
`muted`. La luminosité utilise le `FileView` sysfs déjà employé par le
Control Center, avec un minimum sûr de 10 % et un maximum de 100 %. Ses
écritures sont sérialisées ; la valeur du matériel est relue après chaque
écriture, y compris si le pilote arrondit. L'absence de sortie audio ou de
rétroéclairage désactive l'icône concernée.

Le libellé `RESIZE` en Catppuccin Peach apparaît à gauche des workspaces
quand l'événement IPC Sway `mode` annonce `resize`. Un seul abonnement
`I3IpcListener` partage cet état entre toutes les sorties. Une requête
ponctuelle `get_binding_state` récupère le mode courant au démarrage et à la
reconnexion. L'indicateur n'intervient dans aucun raccourci Sway.

Validation : `qmllint`, `node tests/quickshell/test_scroll_steps.js`,
`sway -C`, `git diff --check`, transition IPC `default → resize → default`,
raccourci `Super+R` puis `Escape` injectés, rechargement QuickShell pendant
`resize`, et inspection visuelle de la barre. Les fonctions des contrôles ont été
appelées temporairement par IPC : PipeWire est passé de 60 à 61 %, et sysfs
de 374815/400000 à 380000/400000 (95 %) ; les niveaux initiaux ont ensuite
été restaurés et le point IPC de test retiré. Aucun geste multitouch physique
n'a été généré par l'automatisation.

### Présentation de la zone droite

La batterie, le volume et la luminosité partagent `PercentIndicatorContent` :
une zone d'icône de 22 px, un écart fixe de 4 px et une valeur alignée à gauche
dans une réserve de 38 px. Le composant mesure 66 × 26 px. La police mono à
12 px affiche partout un espace avant `%` (`9 %`, `10 %`, `99 %`, `100 %`) ;
une donnée indisponible affiche `—`. La réserve empêche le changement de
largeur sans éloigner le nombre de son icône. Les silhouettes des glyphes sont
ajustées individuellement : batterie 21 px, volume 22 px, soleil 23 px.

Le groupe système garde l'ordre Wi-Fi, Bluetooth, batterie, volume,
luminosité, avec 6 px entre indicateurs. Les deux séparateurs utilisent le
même token `Theme.separator`, mesurent 1 × 14 px et disposent chacun de 8 px
de marge latérale. Le tray garde les icônes et menus des applications, avec
des images centrées de 20 × 20 px dans les cibles existantes de 26 × 26 px et
4 px entre cibles. Les actions QuickShell gardent 5 px entre elles ; le bouton
Control Center mesure 30 × 26 px, sans fond au repos et avec un fond discret
au survol ou lorsque le panneau est ouvert.

La zone de défilement du volume et de la luminosité couvre les 66 × 26 px de
chaque indicateur, texte compris.

Validation de la présentation : `qmllint` sur les composants modifiés, tests Node de
`PercentPresentation`, `PercentMath` et `ScrollSteps`, `git diff --check`,
chargement de la configuration par QuickShell et inspection d'une capture de
la barre réelle à l'échelle de la sortie. Les formats 9/10/99/100 % ont été
testés sans modifier les niveaux matériels. Les essais tactiles et visuels de
la série ont également couvert le tray.

### Disposition finale de la zone droite

L'ordre visuel est désormais : Wi-Fi, Bluetooth, batterie, volume,
luminosité ; séparateur ; actions QuickShell, bouton Control Center compris ;
séparateur ; tray applicatif tout à droite. Le second séparateur disparaît
avec un tray vide. Les deux traits visibles utilisent `Theme.separator`,
mesurent 1 × 14 px et sont séparés des groupes par 8 px. Les cibles des
statuts, actions et icônes du tray gardent leur hauteur de 26 px ; les groupes
conservent respectivement 6, 5 et 4 px d'espacement interne.

La police commune des glyphes ne leur donne pas une hauteur de dessin commune :
les formes Wi-Fi, haut-parleur, soleil et réglages occupent moins de hauteur
que les formes Bluetooth et batterie. Les tailles de police sont donc ajustées
sur la barre réelle : Wi-Fi 30 px, Bluetooth 18 px, batterie 18 px, volume
28 px, luminosité 26 px, mises à jour 26 px, presse-papiers 24 px et bouton
Control Center 28 px. L'icône de support amovible conserve ses 18 px et les
images du tray leurs 20 × 20 px. Ces ajustements ne changent ni les zones
interactives, ni les callbacks, ni les contrôleurs du volume et de la
luminosité.

### Accents Catppuccin de la barre

Les pictogrammes utilisent directement les propriétés de `Theme`, alimentées
par l'unique `catppuccin.json` : Wi-Fi connecté `sky`, Bluetooth actif `blue`,
batterie normale `green`, volume non muet `mauve`, luminosité disponible
`yellow`, mises à jour disponibles `peach`, support amovible `teal`,
presse-papiers `pink` et menu système `lavender`. Les nombres et pourcentages
restent en `foreground`. `PercentIndicatorContent` sépare désormais la
couleur du glyphe de celle de la valeur, sans changer ses dimensions.

`StatusColorRoles.js` choisit les rôles selon les états réels, sans contenir
de valeur hexadécimale : Wi-Fi bloqué ou Bluetooth inactif atténués, volume
muet atténué, batterie sous 30 % en avertissement et à 15 % ou moins en
`danger`, erreur de mise à jour ou de support en `danger`, opération de
support en `warningForeground`. Une vérification de mises à jour encore en
attente reste neutre. Les couleurs du tray et les fonds existants ne changent
pas. Les états rares sont vérifiés avec des données isolées par
`tests/quickshell/test_status_color_roles.js`, sans agir sur le matériel.

## Parité avec i3status-rs

| Ancien bloc | QuickShell |
| --- | --- |
| scratchpad indicator | volontairement non repris |
| focused_window | WindowStrip |
| music | Date Center MPRIS |
| bluetooth | status + Control Center |
| net | status + Control Center |
| sound | icône à défilement + Control Center |
| backlight | icône à défilement + Control Center |
| battery | status + page Batterie |
| TLP | PowerProfile |
| packages | Updates |
| time | Clock / Date Center |
| menu | page Session |
