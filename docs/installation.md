# Installation

Ce guide déploie la couche utilisateur depuis un clone neuf. Il n'installe pas
Arch Linux, ne modifie pas `/etc` et n'automatise pas les dépendances externes.
Pour une reconstruction complète, commencer par [Recovery](recovery.md).

## 1. Prérequis

- une installation ArchASP dont la couche système est prête ;
- un compte utilisateur et un `$HOME` sauvegardé avant tout remplacement ;
- Git, GNU Stow et Bash ;
- un accès au dépôt Forgejo ou au miroir GitHub ;
- les paquets examinés dans les inventaires de `.assets/`.

Vérifier les outils avant de continuer :

```bash
git --version
stow --version
bash --version
```

## 2. Cloner

Forgejo est l'upstream principal :

```bash
git clone --recurse-submodules \
  ssh://git@git.labfytools.com:2223/fy59/Dotfiles_ArchAP.git \
  "$HOME/.dotfiles"
cd "$HOME/.dotfiles"
```

Le miroir public peut servir de source de récupération :

```bash
git clone --recurse-submodules \
  https://github.com/labfytools/Dotfiles_ArchAP.git \
  "$HOME/.dotfiles"
cd "$HOME/.dotfiles"
```

Pour restaurer le snapshot stable plutôt que `main` :

```bash
git switch 0.1.0
```

## 3. Vérifier les sous-modules

```bash
git submodule update --init --recursive
git submodule status --recursive
```

Une ligne commençant par `-` indique un sous-module non initialisé ; une ligne
commençant par `+` indique un commit différent de celui épinglé.

## 4. Examiner les inventaires

Les listes Pacman et AUR sont des snapshots, pas des commandes aveugles à
installer. Comparer leur contenu à la machine cible et lire
[`packages.md`](packages.md) ainsi que
[`external-tools.md`](../.assets/external-tools.md) avant toute installation.

## 5. Définir les 31 packages Stow

Les commandes suivantes sont destinées à Bash :

```bash
packages=(
  atuin bat bin btop cliphist eza fastfetch fzf gtk-3.0 gtklock
  hyprwhspr i3status-rust icons kitty mako nvim opencode qt5ct qt6ct
  starship sway swaylock systemd themes tmux uwsm wallpapers wofi yazi
  ytmusic-tui zsh
)

printf '%s\n' "${packages[@]}"
```

`docs/` et `.assets/` ne doivent pas être ajoutés à ce tableau.

## 6. Effectuer le dry-run

Depuis la racine du dépôt :

```bash
stow --no --verbose=2 --target="$HOME" "${packages[@]}"
```

Lire chaque conflit. Un fichier réel déjà présent à la cible peut masquer ou
bloquer un lien Stow ; le sauvegarder et décider explicitement de sa source
avant le déploiement. Ne pas utiliser d'option d'adoption sans audit préalable.

## 7. Déployer

Une fois le dry-run accepté :

```bash
stow --verbose=2 --target="$HOME" "${packages[@]}"
```

Cette commande crée ou met à jour des liens sous `$HOME`. Elle ne doit pas être
exécutée depuis une autre racine ni avec `.` comme nom de package.

## 8. Recharger systemd user

Les liens d'activation versionnés dans le package `systemd` expriment les
unités utilisateur attendues. Recharger et vérifier avant tout démarrage :

```bash
systemctl --user daemon-reload
systemd-analyze --user verify \
  "$HOME"/.config/systemd/user/*.service \
  "$HOME"/.config/systemd/user/*.timer
systemctl --user --failed
```

Certaines unités dépendent de projets externes. Ne les démarrer que lorsque
leurs chemins et configurations locales existent ; voir [`systemd.md`](systemd.md).

## 9. Valider

```bash
git status --short
git submodule status --recursive
find "$HOME/.config" -xtype l -print
systemctl --user --failed
sway --validate --config "$HOME/.config/sway/config"
```

La dernière commande nécessite Sway installé. Un lien cassé ou une unité en
échec doit être diagnostiqué avant de considérer la restauration terminée.
