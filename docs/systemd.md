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
| idle | `swayidle.service` | verrouillage, alimentation des sorties et pause média |
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

## Supports amovibles USB/SD

`labfy-removable-media.service` appartient au package Stow `systemd` et son
exécutable `labfy-removable-media`, ainsi que le client
`labfy-removable-mediactl`, appartiennent au package `bin`. Après le déploiement
de ces deux packages, le lien versionné dans
`wayland-session@sway.desktop.target.wants/` démarre le service avec la session
Sway. L'unité est rattachée à `wayland-session@sway.desktop.target`, redémarre
sur échec et n'est pas un service système.

Le daemon observe l'ObjectManager UDisks du bus système et publie son état
runtime JSON V1 dans `$XDG_RUNTIME_DIR/labfy-removable-media.json`. Son socket
Unix `$XDG_RUNTIME_DIR/labfy-removable-media.sock` et le snapshot sont créés
avec le mode `0600`. L'IPC n'accepte qu'une requête JSON
terminée par LF pour `list`, `mount`, `unmount`, `open` ou `safe-remove` ; les
identifiants runtime sont relus dans UDisks avant toute mutation.

Seuls les systèmes de fichiers des lecteurs USB ou SD/MMC sont présentés. Les
blocs `HintIgnore` et `HintSystem`, ainsi que les volumes `crypto_LUKS`, sont
exclus ; aucun déverrouillage LUKS n'est tenté. MTP ne relève pas de ce contrat
UDisks `Block`/`Filesystem` et n'est pas pris en charge. Un objet UDisks
nouvellement présent est monté au plus une fois : un échec est isolé des autres
volumes, et une nouvelle tentative automatique demande une disparition puis une
réinsertion de l'objet. Un démontage manuel ne provoque donc pas de remontage
sur un événement de propriétés ultérieur.

La commande `safe-remove` porte sur le lecteur : elle démonte d'abord tous ses
systèmes de fichiers, y compris ceux masqués par l'interface, puis relit leur
état avant d'appeler `PowerOff` ou `Eject`.

Après Stow et le rechargement de systemd user, vérifier l'unité et exécuter les
tests synthétiques sans périphérique réel :

```bash
systemctl --user daemon-reload
systemd-analyze --user verify \
  "$HOME"/.config/systemd/user/labfy-removable-media.service
systemctl --user is-enabled labfy-removable-media.service
python3 -B -m unittest discover -s tests/removable_media -p 'test_*.py'
```

Les tests utilisent des backends et sockets synthétiques. Ils couvrent le
filtrage UDisks, l'automontage borné, les opérations par volume ou lecteur, le
contrat JSON et les limites de l'IPC, mais ne constituent pas une validation sur
matériel USB/SD réel. Cette validation n'a pas encore été effectuée.

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
