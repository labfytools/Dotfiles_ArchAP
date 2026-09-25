# Packages et inventaires

Les fichiers de `.assets/` sont des snapshots de reconstruction. Ils décrivent
l'état observé ; ils ne garantissent ni l'ordre d'installation ni la présence
des données et projets externes.

## Inventaires

| Fichier | Contenu | Source principale |
| --- | --- | --- |
| `.assets/pkglist-pacman.txt` | paquets officiels explicitement installés | `pacman -Qqen` |
| `.assets/pkglist-aur.txt` | paquets foreign/AUR explicitement installés | `pacman -Qqem` |
| `.assets/enabled-services.txt` | services système activés | `systemctl list-unit-files` |
| `.assets/enabled-system-aux-units.txt` | timers, sockets et paths système activés | `systemctl list-unit-files` |
| `.assets/enabled-user-aux-units.txt` | timers, sockets et paths utilisateur activés | `systemctl --user list-unit-files` |
| [`.assets/external-tools.md`](../.assets/external-tools.md) | outils Cargo/npm, builds, projets et helpers locaux | inventaire manuel vérifié |

## Régénérer les listes de paquets

Depuis la racine du dépôt, après avoir contrôlé que la machine représente bien
l'état à documenter :

```bash
pacman -Qqen | LC_ALL=C sort > .assets/pkglist-pacman.txt
pacman -Qqem | LC_ALL=C sort > .assets/pkglist-aur.txt
```

`pkglist-aur.txt` signifie techniquement « paquets étrangers à la base de
données sync ». Il peut contenir un paquet construit localement et pas
nécessairement publié dans l'AUR. Chaque entrée doit donc être examinée.

## Régénérer les snapshots systemd

```bash
systemctl list-unit-files --type=service --state=enabled \
  --no-legend --no-pager | awk '{print $1}' | LC_ALL=C sort

systemctl list-unit-files --type=socket,path,timer --state=enabled \
  --no-legend --no-pager | awk '{print $1}' | LC_ALL=C sort

systemctl --user list-unit-files --type=socket,path,timer --state=enabled \
  --no-legend --no-pager | awk '{print $1}' | LC_ALL=C sort
```

Comparer d'abord la sortie aux fichiers versionnés. Certaines unités
instanciées ou activations liées à la machine peuvent demander une revue
manuelle ; ne pas remplacer un inventaire uniquement parce qu'une commande
instantanée diffère.

## Restaurer avec discernement

Les listes peuvent aider à préparer une commande Pacman, mais le dépôt ne
promet pas une restauration non interactive. Sur une machine neuve :

1. restaurer d'abord la base système via `arch-system` ;
2. examiner les paquets officiels encore voulus ;
3. reconstruire les paquets étrangers avec une source AUR ou locale vérifiée ;
4. restaurer séparément les outils Cargo/npm de
   [`.assets/external-tools.md`](../.assets/external-tools.md) ;
5. reconstruire ou cloner les projets externes à leurs chemins attendus ;
6. vérifier les exécutables référencés par Sway, Zsh, les scripts et systemd.

Les credentials, bases applicatives et caches ne doivent jamais être ajoutés
aux inventaires de paquets.
