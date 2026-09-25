# Outils hors Pacman

Cet inventaire décrit les dépendances observées le 25 septembre 2026 qui ne
sont pas restaurées par `pkglist-pacman.txt` ou `pkglist-aur.txt`.

## Cargo

- `ytmusic-tui 0.2.1` (`cargo install ytmusic-tui`)

## npm utilisateur

Le préfixe actif est `~/.local/npm` et `.zshrc` l'ajoute à `PATH`.

- `@earendil-works/pi-coding-agent@0.84.3`
- `context-mode@1.0.169`
- `prettier@3.9.6`

## Builds et projets locaux

Ces éléments sont volontairement hors du dépôt de dotfiles. Les liens ou
unités du dépôt supposent leur présence à ces emplacements :

- `~/.local/src/arch-sentinel` fournit `~/.local/bin/arch-sentinel` ;
- `~/Documents/Development/trainlog` fournit les exécutables et agents Trainlog ;
- `~/Documents/Lardon` fournit la session FreeCAD et ses outils ;
- `~/Documents/Development/labfy-remote-ui` fournit `labfy-remote-ui` ;
- `~/.local/opt/openmvs-2.4.0` fournit OpenMVS au pipeline `scan3d` ;
- `~/.codex/packages/standalone/current` fournit le lien utilisateur `codex`.

## Helpers système locaux

Ces fichiers sous `/usr/local` ne sont possédés par aucun paquet. Ils relèvent
de la couche système `arch-system`, pas de ce dépôt utilisateur :

- `/usr/local/sbin/batlimit-set` ;
- `/usr/local/sbin/vmware-stack`.

## Problème système connu

`wg-quick@wg0.service` est activé mais échoue au démarrage car `resolvconf`
signale une divergence de signature pour `/etc/resolv.conf`. La correction
appartient à `arch-system` et n'est pas appliquée ici.
