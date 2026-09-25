<p align="center">
  <img src=".assets/screen.jpg" alt="ArchASP — Sway desktop" width="100%">
</p>

<h1 align="center">ArchASP Dotfiles</h1>

<p align="center">
  Configuration utilisateur reproductible pour une station Arch Linux sous
  Wayland, déployée package par package avec GNU Stow.
</p>

<p align="center">
  <code>Arch Linux</code> · <code>Sway</code> · <code>GNU Stow</code> ·
  <code>systemd --user</code> · <code>Zsh</code>
</p>

<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#desktop-stack">Desktop</a> ·
  <a href="#shell-stack">Shell</a> ·
  <a href="#repository-layout">Layout</a> ·
  <a href="#deployment">Deployment</a> ·
  <a href="#rebuilding-archasp">Rebuild</a>
</p>

<a id="overview"></a>

## ✦ Overview

Ce dépôt contient la couche **utilisateur** d'ArchASP : session graphique,
applications terminal, shell, scripts personnels et unités systemd user. La
couche **système/root** est volontairement séparée.

| Dépôt | Responsabilité |
| --- | --- |
| **`.dotfiles`** | Sway, Kitty, Neovim, Zsh, scripts, thèmes et services utilisateur |
| **[`arch-system`](https://git.labfytools.com/fy59/arch-system)** | Installation Arch, boot, stockage, réseau, paquets, `/etc` et helpers root |

Cette séparation évite de mêler état personnel et administration système. Le
dépôt reste néanmoins spécifique à la machine : sorties Sway, périphériques,
chemins sous `/home/fy59` et projets externes doivent être relus avant un
déploiement ailleurs.

<a id="desktop-stack"></a>

## ✦ Desktop Stack

```text
greetd
  └─ tuigreet
      └─ UWSM
          └─ Sway
              ├─ Swaybar ── i3status-rs
              ├─ Mako       notifications
              ├─ Wofi       launcher
              ├─ Swaylock   verrouillage
              ├─ Cliphist   historique du presse-papiers
              └─ Kitty      terminal
```

| Fonction | Composant canonique |
| --- | --- |
| Session | `greetd → tuigreet → uwsm start default → sway.desktop` |
| Compositor | Sway / SwayFX |
| Barre | Swaybar avec i3status-rs |
| Notifications | Mako |
| Launcher | Wofi |
| Verrouillage et idle | Swaylock + swayidle |
| Presse-papiers | wl-clipboard + Cliphist |
| Terminal | Kitty |
| Profils d'énergie | TLP via l'interface utilisateur `tlpctl` |

`uwsm/.config/uwsm/default-id` sélectionne `sway.desktop`. La copie de
référence de greetd se trouve dans `.assets/greetd/config.toml`; son
installation sous `/etc/greetd` appartient à `arch-system`.

<a id="shell-stack"></a>

## ✦ Shell Stack

```text
Zsh
 ├─ Starship
 ├─ Atuin
 ├─ FZF
 ├─ Zoxide
 ├─ Eza
 ├─ Bat
 └─ Yazi
```

`.zprofile` démarre la session graphique via UWSM lorsque celui-ci autorise un
démarrage. `.zshenv` publie le socket de l'agent SSH utilisateur. L'historique,
les bases et la clé Atuin restent strictement locaux et hors Git.

<a id="repository-layout"></a>

## ✦ Repository Layout

Chaque répertoire de premier niveau, hors `.assets` et `.git`, est un package
GNU Stow indépendant. Son arborescence reproduit le chemin attendu depuis
`$HOME`.

```text
.dotfiles/
├── sway/.config/sway/             → ~/.config/sway/
├── i3status-rust/.config/         → ~/.config/i3status-rust/
├── kitty/.config/kitty/           → ~/.config/kitty/
├── nvim/.config/nvim/             → ~/.config/nvim/
├── systemd/.config/systemd/user/  → ~/.config/systemd/user/
├── bin/.local/bin/                → ~/.local/bin/
├── zsh/.zshrc                     → ~/.zshrc
├── zsh/.zprofile                  → ~/.zprofile
└── .assets/                       inventaires et références, non déployés
```

### Packages principaux

| Groupe | Packages Stow |
| --- | --- |
| Desktop | `sway`, `swaylock`, `mako`, `wofi`, `cliphist`, `i3status-rust` |
| Terminal et shell | `kitty`, `zsh`, `starship`, `atuin`, `fzf`, `eza`, `bat`, `yazi` |
| Développement | `nvim`, `tmux`, `opencode`, `bin` |
| Services | `systemd`, `uwsm` |
| Apparence | `gtk-3.0`, `gtklock`, `qt5ct`, `qt6ct`, `themes`, `icons`, `wallpapers` |
| Outils | `btop`, `fastfetch`, `hyprwhspr`, `ytmusic-tui` |

Les thèmes, icônes et wallpapers sont volontairement versionnés. Les
exécutables issus de projets externes restent hors Git même lorsqu'un script
ou une unité user les utilise.

### Sous-modules

Les plugins Zsh et Tmux sont épinglés par Git :

| Intégration | Chemin |
| --- | --- |
| Fast Syntax Highlighting | `zsh/.zsh/plugins/fast-syntax-highlighting` |
| FZF Tab | `zsh/.zsh/plugins/fzf-tab` |
| Zsh Autosuggestions | `zsh/.zsh/plugins/zsh-autosuggestions` |
| Catppuccin Tmux | `tmux/.config/tmux/plugins/catppuccin/tmux` |

<a id="deployment"></a>

## ✦ Deployment

### Prérequis

- Git ;
- GNU Stow ;
- les paquets décrits dans `.assets` ;
- une sauvegarde des fichiers existants qui pourraient entrer en conflit.

### Clone

```bash
git clone --recurse-submodules \
  ssh://git@git.labfytools.com:2223/fy59/Dotfiles_ArchAP.git \
  "$HOME/.dotfiles"

cd "$HOME/.dotfiles"
git submodule update --init --recursive
```

### Dry-run Stow

Construire la liste des packages à partir des répertoires de premier niveau :

```bash
mapfile -t packages < <(
  find . -mindepth 1 -maxdepth 1 -type d \
    ! -name .git ! -name .assets -printf '%f\n' | sort
)

stow --no --verbose=2 --target="$HOME" "${packages[@]}"
```

Examiner tout conflit avant le déploiement réel :

```bash
stow --verbose=2 --target="$HOME" "${packages[@]}"
```

> Stow reçoit les **noms des packages**. La racine du dépôt n'est pas un
> package : ne pas utiliser `stow .`.

<a id="package-inventory"></a>

## ✦ Package Inventory

| Fichier | Source | Contenu |
| --- | --- | --- |
| `.assets/pkglist-pacman.txt` | `pacman -Qqen` | Paquets officiels explicitement installés |
| `.assets/pkglist-aur.txt` | `pacman -Qqem` | Paquets foreign/AUR explicitement installés |
| `.assets/enabled-services.txt` | systemd système | Services système activés |
| `.assets/enabled-system-aux-units.txt` | systemd système | Timers, sockets et paths activés |
| `.assets/enabled-user-aux-units.txt` | systemd user | Timers, sockets et paths utilisateur activés |
| `.assets/external-tools.md` | inventaire manuel | Cargo, npm, builds locaux, projets et helpers `/usr/local` |

Ces fichiers sont des instantanés vérifiables, pas un installateur. Les paquets
AUR, outils Cargo/npm et builds locaux doivent être restaurés séparément.

<a id="services"></a>

## ✦ Services

Le package `systemd` contient les unités utilisateur ainsi que leurs liens
d'activation relatifs. Il couvre notamment Cliphist, swayidle, GNOME Keyring,
l'agent SSH, les notifications de batterie et les intégrations Trainlog,
Lardon et Arch Sentinel.

Après une modification :

```bash
systemctl --user daemon-reload
systemd-analyze --user verify ~/.config/systemd/user/*.service
```

Certaines unités lancent du code externe au dépôt. Leurs chemins et
dépendances sont documentés dans `.assets/external-tools.md`. Les services
système et toute modification de `/etc` restent sous la responsabilité
d'`arch-system`.

<a id="secrets"></a>

## ✦ Secrets

Ce dépôt n'a pas vocation à contenir :

- clés SSH, GPG, WireGuard ou Atuin ;
- `.netrc`, mots de passe, tokens, cookies ou credentials ;
- configurations privées Rclone, GitHub CLI ou Nextcloud ;
- bases de données, historiques shell ou états applicatifs personnels.

Les ignorer dans le HEAD ne suffit pas : un secret déjà commité doit être
renouvelé, puis supprimé de tout l'historique avant publication.

<a id="rebuilding-archasp"></a>

## ✦ Rebuilding ArchASP

```text
┌──────────────────────────────────────────────────────┐
│ arch-system                                          │
│ Arch · boot · stockage · réseau · paquets · /etc    │
└──────────────────────────┬───────────────────────────┘
                           │ socle système prêt
                           ▼
┌──────────────────────────────────────────────────────┐
│ .dotfiles                                            │
│ Stow · session · shell · scripts · systemd user     │
└──────────────────────────┬───────────────────────────┘
                           │ restaurations externes
                           ▼
┌──────────────────────────────────────────────────────┐
│ AUR · Cargo/npm · projets locaux · secrets · données│
└──────────────────────────────────────────────────────┘
```

Ordre de reconstruction recommandé :

1. restaurer la couche système avec `arch-system` ;
2. installer Git et GNU Stow ;
3. cloner ce dépôt avec ses sous-modules ;
4. restaurer les paquets officiels puis examiner les paquets AUR ;
5. effectuer le dry-run et déployer les packages Stow ;
6. restaurer les outils Cargo/npm et les projets locaux nécessaires ;
7. restaurer les secrets et données applicatives depuis une sauvegarde sûre ;
8. valider puis activer les unités systemd voulues.

Le dépôt ne reconstruit pas seul les projets sous `Documents`, OpenMVS local,
les helpers `/usr/local`, les secrets, les bases applicatives ou les réglages
matériels propres à la machine.

<a id="repository-mirrors"></a>

## ✦ Repository Mirrors

| Rôle | Hébergement | URL |
| --- | --- | --- |
| Upstream principal | Forgejo | `ssh://git@git.labfytools.com:2223/fy59/Dotfiles_ArchAP.git` |
| Miroir public | GitHub | `https://github.com/labfytools/Dotfiles_ArchAP` |

Le fetch d'`origin` reste attaché à Forgejo. Ses URLs de push publient vers
Forgejo et GitHub afin qu'un `git push origin main` maintienne les deux copies.

<a id="license"></a>

## ✦ License

Aucune licence n'est actuellement déclarée pour ce dépôt.
