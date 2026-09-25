# ArchASP Dotfiles

Configuration de la couche utilisateur de la station Arch Linux ArchASP. Le
dépôt privilégie des fichiers lisibles, déployés par GNU Stow, et sépare
explicitement la session utilisateur de l'administration système.

## Overview

Ce dépôt gère Sway, les applications de terminal, le shell, les scripts
personnels et les unités systemd utilisateur. La configuration root, les
paquets de base, le stockage, le réseau, le boot et les helpers sous
`/usr/local` appartiennent au dépôt
[`arch-system`](https://git.labfytools.com/fy59/arch-system).

Certaines configurations restent liées à cette machine : sorties Sway,
périphériques, chemins sous `/home/fy59` et projets présents dans `Documents`.
Elles doivent être relues avant un déploiement sur un autre poste.

## Desktop Stack

La chaîne de session canonique est :

```text
greetd -> tuigreet -> UWSM -> Sway
```

Sway utilise sa barre native avec i3status-rs. Mako fournit les notifications,
Wofi le lanceur, Swaylock le verrouillage, wl-clipboard et Cliphist
l'historique du presse-papiers, et Kitty le terminal.

Le fichier `uwsm/.config/uwsm/default-id` sélectionne `sway.desktop`. La copie
de référence de la configuration root de greetd se trouve dans
`.assets/greetd/config.toml`; son installation réelle sous `/etc/greetd`
relève de `arch-system`.

## Shell Stack

Le shell interactif est Zsh. Son environnement associe Starship, Atuin, FZF,
Zoxide, Eza, Bat et Yazi. `.zprofile` démarre la session graphique via UWSM
lorsque celui-ci autorise un démarrage, et `.zshenv` publie le socket de
l'agent SSH utilisateur.

Les données Atuin, historiques de shell, clés, bases et états applicatifs ne
font pas partie du dépôt.

## Repository Layout

Chaque répertoire de premier niveau, hors `.assets` et `.git`, est un paquet
GNU Stow indépendant. Son contenu reproduit le chemin attendu depuis `$HOME` :

```text
kitty/.config/kitty/       -> ~/.config/kitty/
nvim/.config/nvim/         -> ~/.config/nvim/
sway/.config/sway/         -> ~/.config/sway/
bin/.local/bin/            -> ~/.local/bin/
systemd/.config/systemd/   -> ~/.config/systemd/
zsh/.zshrc                 -> ~/.zshrc
```

Les thèmes, icônes et wallpapers sont volontairement versionnés. `.assets`
contient les inventaires de reconstruction et des références système ; ce
n'est pas un paquet Stow.

## Deployment

Prérequis : Git, GNU Stow et les paquets décrits dans `.assets`. Cloner le
dépôt principal avec ses sous-modules :

```bash
git clone --recurse-submodules \
  ssh://git@git.labfytools.com:2223/fy59/Dotfiles_ArchAP.git \
  "$HOME/.dotfiles"
cd "$HOME/.dotfiles"
git submodule update --init --recursive
```

Construire la liste des paquets, puis commencer obligatoirement par un dry-run :

```bash
mapfile -t packages < <(
  find . -mindepth 1 -maxdepth 1 -type d \
    ! -name .git ! -name .assets -printf '%f\n' | sort
)
stow --no --verbose=2 --target="$HOME" "${packages[@]}"
```

Après examen des conflits éventuels, effectuer le déploiement :

```bash
stow --verbose=2 --target="$HOME" "${packages[@]}"
```

Stow reçoit les noms des paquets. Il ne faut pas lancer `stow .`, car la
racine du dépôt n'est pas elle-même un paquet.

## Package Inventory

- `.assets/pkglist-pacman.txt` contient les paquets officiels explicitement
  installés (`pacman -Qqen`).
- `.assets/pkglist-aur.txt` contient les paquets foreign/AUR explicitement
  installés (`pacman -Qqem`).
- `.assets/external-tools.md` décrit Cargo, npm, builds manuels, projets locaux
  et helpers système qui ne sont pas restaurés par Pacman.

Ces fichiers sont des instantanés, pas un programme d'installation. Leur
application et la validation des paquets AUR relèvent de la reconstruction du
système.

## Services

`.assets/enabled-services.txt` recense les services systemd système activés.
Les timers, sockets et paths sont séparés dans
`.assets/enabled-system-aux-units.txt` et
`.assets/enabled-user-aux-units.txt`. Leur activation côté système appartient
à `arch-system`.

Le paquet `systemd` contient les unités utilisateur et leurs liens
d'activation canoniques. Après déploiement ou modification :

```bash
systemctl --user daemon-reload
systemd-analyze --user verify ~/.config/systemd/user/*.service
```

Plusieurs unités lancent du code externe à ce dépôt, notamment Trainlog,
Lardon et Arch Sentinel. Leurs sources et builds doivent être restaurés aux
emplacements documentés dans `.assets/external-tools.md`.

## Secrets

Ne jamais versionner de clé SSH/GPG, `.netrc`, token, cookie, credential,
configuration Rclone ou `gh` privée, clé WireGuard, base Atuin, clé Atuin ou
secret Nextcloud. Les états et caches applicatifs restent sous `$HOME` et sont
exclus de Stow ou de Git.

Un contrôle du HEAD ne remplace pas une analyse de l'historique Git. Tout
secret ayant été commité doit être révoqué ou renouvelé avant une purge de
l'historique et avant la publication d'un miroir.

## Rebuilding ArchASP

Une reconstruction repose sur deux couches :

1. `arch-system` restaure la base Arch, les paquets, greetd, le réseau, le
   stockage et les services root ;
2. ce dépôt restaure les sous-modules, fichiers Stow, scripts et unités
   systemd utilisateur.

Restent manuels ou externes : installation des paquets AUR, outils Cargo/npm,
builds des projets dans `Documents`, OpenMVS local, helpers `/usr/local`,
secrets, données applicatives et activation contrôlée des unités. Le dépôt ne
prétend donc pas reconstruire seul une machine complète.

## Repository Mirrors

Forgejo est l'upstream principal et conserve le nom de remote `origin`.
GitHub, lorsqu'il sera configuré, sera un miroir secondaire nommé `github`.
Un historique contenant un secret ne doit jamais être envoyé vers ce miroir.

## License

Aucune licence n'est actuellement déclarée pour ce dépôt.
