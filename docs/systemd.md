# systemd

## Deux périmètres distincts

| Périmètre | Commande | Propriété |
| --- | --- | --- |
| système | `systemctl ...` | `arch-system`, `/etc/systemd/system`, services root |
| utilisateur | `systemctl --user ...` | package Stow `systemd`, `~/.config/systemd/user` |

Le dépôt conserve dans `.assets/enabled-services.txt` et
`.assets/enabled-system-aux-units.txt` des snapshots de la couche système,
mais il ne l'active pas. Les unités effectivement versionnées sous
`systemd/.config/systemd/user/` appartiennent à la couche utilisateur.

## Unités utilisateur canoniques

| Domaine | Unités | Fonction |
| --- | --- | --- |
| session | `gnome-keyring-daemon.service`, `ssh-agent.service`, `wlsunset.service` | agents et services de session |
| desktop | `quickshell-labfy-sway.service`, `labfy-quickshell-updates.service/.timer`, `labfy-removable-media.service` | barre, notifications, vérification des mises à jour et gestion des supports amovibles |
| clipboard | `cliphist-text.service`, `cliphist-image.service` | collecte texte et images Wayland |
| idle | `swayidle.service`, `labfy-idle-bridge.service` | verrouillage, alimentation des sorties et pause média ; relais des demandes applicatives d'inhibition vers QuickShell |
| batterie | `battery-low-notify.service/.timer` | contrôle et notification périodiques |
| maintenance | `clean-makepkg.service` | nettoyage du cache temporaire utilisateur |
| Arch Sentinel | `arch-sentinel-sample.service/.timer` | collecte périodique légère |
| Trainlog | `trainlog-btd.service`, `trainlog-syncd.service`, `trainlog-web.service` | intégrations locales facultatives |
| Lardon | `lardon-freecad.service` | session FreeCAD liée au projet externe |
| autres | `hyprwhspr.service`, `protonmail-bridge.service` | intégrations déclenchées selon l'usage |

Les liens versionnés dans `default.target.wants/`,
`graphical-session.target.wants/`, `wayland-session@sway.desktop.target.wants/`
et `timers.target.wants/` expriment les
activations utilisateur retenues. `.assets/enabled-user-aux-units.txt` capture
en complément les timers et sockets activés observés sur la machine.

`labfy-idle-bridge.service` est une unité utilisateur voulue par
`wayland-session@sway.desktop.target`, ordonnée après
`quickshell-labfy-sway.service`. Elle fournit le destinataire
`org.freedesktop.ScreenSaver` que le backend GTK du portail sollicite pour
les demandes `Inhibit`. Le helper Python/Gio communique avec QuickShell par
socket privée et ne modifie pas `swayidle.service`. Voir
[portal/README.md](../portal/README.md) pour les cookies, la récupération
après déconnexion et le retour arrière.

`swayidle.service` utilise `/home/fy59/.local/bin/labfy-lock` pour le délai
de verrouillage de 300 s et `before-sleep`, après la pause média. Le wrapper
attend la confirmation `secure` avant de rendre la main à `swayidle -w`.
Les autres délais et commandes d'inactivité sont conservés. La politique
PAM dédiée provient de `system/pam.d/labfy-lock` et s'installe en tant que
`/etc/pam.d/labfy-lock` avant un nouveau déploiement du verrou. La procédure
historique de retour à `swaylock` est documentée dans
[labfy-lock/README.md](../quickshell/.config/quickshell/labfy-lock/README.md).

## Supports amovibles USB/SD et MTP

`labfy-removable-media.service` appartient au package Stow `systemd` et son
exécutable `labfy-removable-media`, ainsi que le client
`labfy-removable-mediactl`, appartiennent au package `bin`. Après le déploiement
de ces deux packages, le lien versionné dans
`wayland-session@sway.desktop.target.wants/` démarre le service avec la session
Sway. L'unité est rattachée à `wayland-session@sway.desktop.target`, redémarre
sur échec et n'est pas un service système.

Un seul daemon de session assure le cycle de vie, le socket et le snapshot de
`labfy-removable-media`. Il observe l'ObjectManager UDisks du bus système pour
les lecteurs USB et SD/MMC, et `Gio.VolumeMonitor`/GVFS-MTP pour les
téléphones. Il publie le snapshot JSON `labfy.removable-media` version `2`
dans `$XDG_RUNTIME_DIR/labfy-removable-media.json`. Son socket Unix
`$XDG_RUNTIME_DIR/labfy-removable-media.sock` et le snapshot sont créés avec le
mode `0600`. L'IPC n'accepte qu'une requête JSON terminée par LF pour `list`,
`mount`, `unmount`, `open` ou `safe-remove` ; les identifiants runtime opaques
sont relus dans leur backend avant toute mutation.

Seuls les systèmes de fichiers des lecteurs USB ou SD/MMC éligibles et les
volumes MTP détectés par GVFS sont présentés. Pour UDisks, les blocs
`HintIgnore` et `HintSystem`, ainsi que les volumes `crypto_LUKS`, sont exclus ;
aucun déverrouillage LUKS n'est tenté. Pendant la vie du daemon, chaque support
présent est monté automatiquement au plus une fois : un échec est isolé des
autres supports, et une nouvelle tentative automatique demande une disparition
puis une réinsertion. Pendant cette même vie, un démontage manuel ne provoque
donc pas de remontage sur un événement de propriétés ultérieur. Au démarrage ou
au redémarrage, le cold-start V1 effectue un nouveau scan : un téléphone déjà
présent peut alors être monté. Pour MTP, le montage et cette règle de présence
reposent sur GVFS.

Le schéma V2 publie des identifiants MTP opaques, `kind` et `actions`. Chaque
appareil publie aussi `safe_remove_runtime_id`, y compris lorsque `safe-remove`
n'est pas disponible. Il ne publie pas d'URI MTP ni de champ d'identité
matérielle. Pour ouvrir un support, UDisks fournit son véritable point de
montage ; le chemin du `GMount` est réservé à MTP. Ce chemin, conservé dans le
snapshot privé (`0600`), peut contenir un identifiant intégré par GVFS. La
commande `safe-remove` UDisks porte sur le lecteur : elle
démonte d'abord tous ses systèmes de fichiers, y compris ceux masqués par
l'interface, puis relit leur état avant d'appeler `PowerOff` ou `Eject`. Pour
MTP, `safe-remove` ferme logiquement le montage GVFS ; il n'appelle ni
`PowerOff` ni `Eject`.

Après Stow et le rechargement de systemd user, vérifier l'unité et exécuter les
tests synthétiques sans périphérique réel :

```bash
systemctl --user daemon-reload
systemd-analyze --user verify \
  "$HOME"/.config/systemd/user/labfy-removable-media.service
systemctl --user is-enabled labfy-removable-media.service
python3 -B -m unittest discover -s tests/removable_media -p 'test_*.py'
```

Les 29 tests `unittest` utilisent des backends et sockets synthétiques. Ils
couvrent le filtrage UDisks, le cycle de vie MTP/GVFS, l'automontage borné, les
opérations par volume ou lecteur, le contrat JSON V2 et les limites de l'IPC.
Ils sont passants. Le `qmllint` est également passant. Ces validations
logicielles ne constituent pas une recette UI sur matériel MTP : celle-ci reste
à effectuer. Un Samsung réel a été reconnu et les opérations ciblées de montage
et de retrait en sécurité ont été vérifiées dans le code isolé. La validation
matérielle USB Ventoy V1 avait été effectuée avant le commit précédent.

La gestion des supports amovibles est indépendante de Session Restore : elle ne
participe ni aux checkpoints, ni au choix de restauration au démarrage.

## Dépendances externes

Les unités Trainlog, Lardon et Arch Sentinel supposent que leurs projets ou
binaires existent aux chemins décrits dans
[`external-tools.md`](../.assets/external-tools.md).
Certaines unités Trainlog sont conditionnées par une configuration locale.
Ces fichiers de configuration et leurs éventuels secrets ne sont pas
versionnés.

Une unité absente du projet externe peut rester valide syntaxiquement tout en
échouant à l'exécution. La restauration doit donc vérifier à la fois le fichier
d'unité et son `ExecStart`.

## Validation

Après déploiement Stow :

```bash
systemctl --user daemon-reload
systemd-analyze --user verify \
  "$HOME"/.config/systemd/user/*.service \
  "$HOME"/.config/systemd/user/*.timer
systemctl --user list-unit-files --state=enabled
systemctl --user --failed
```

Ne pas lancer ou activer en bloc toutes les unités : celles liées à des
projets externes sont facultatives et peuvent exiger une configuration locale.
Les modifications des services système se font dans `arch-system`, jamais par
une commande `systemctl` non documentée dans ce dépôt.
