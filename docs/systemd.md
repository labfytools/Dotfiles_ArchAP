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
| clipboard | `cliphist-text.service`, `cliphist-image.service` | collecte texte et images Wayland |
| idle | `swayidle.service` | verrouillage, alimentation des sorties et pause média |
| batterie | `battery-low-notify.service/.timer` | contrôle et notification périodiques |
| maintenance | `clean-makepkg.service` | nettoyage du cache temporaire utilisateur |
| Arch Sentinel | `arch-sentinel-sample.service/.timer` | collecte périodique légère |
| Trainlog | `trainlog-btd.service`, `trainlog-syncd.service`, `trainlog-web.service` | intégrations locales facultatives |
| Lardon | `lardon-freecad.service` | session FreeCAD liée au projet externe |
| autres | `hyprwhspr.service`, `protonmail-bridge.service` | intégrations déclenchées selon l'usage |

Les liens versionnés dans `default.target.wants/`,
`graphical-session.target.wants/` et `timers.target.wants/` expriment les
activations utilisateur retenues. `.assets/enabled-user-aux-units.txt` capture
en complément les timers et sockets activés observés sur la machine.

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
