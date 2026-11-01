# Icônes et curseurs : dépendances système

Le dépôt ne versionne plus les copies complètes des thèmes tiers (environ
292 000 entrées Git et 1,3 Go sur la machine auditée au 1er novembre 2026).
Ces collections amont alourdissaient chaque clone et chaque index de worktree,
sans être des configurations personnelles.

## Thèmes utilisés sur ArchASP

- GTK sélectionne `Tela-circle-blue` (à contrôler par
  `gsettings get org.gnome.desktop.interface icon-theme`).
- Le dock et le menu QuickShell utilisent `Tela-circle-purple-dark`
  (défini par `quickshell/.config/quickshell/labfy-sway/applications/shared.py`).
- Ces thèmes sont présents sous `/usr/share/icons` et possédés par les
  paquets `tela-circle-icon-theme-blue` et
  `tela-circle-icon-theme-purple`. Le paquet
  `tela-circle-icon-theme-all` est également installé sur ArchASP.
- Bibata est disponible grâce à `bibata-cursor-theme`.

## Réinstallation

Installer les thèmes nécessaires par Pacman/AUR (en fonction des dépôts
configurés), puis vérifier la présence des chemins sous `/usr/share/icons`.
Les inventaires `.assets/pkglist-pacman.txt` et `.assets/pkglist-aur.txt`
documentent les familles Tela Circle et Bibata.

Il ne faut plus exécuter `stow icons` : le package `icons` est retiré du
tableau des packages actifs. La présence de thèmes dans le répertoire système
est indépendante de GNU Stow.

## Migration de la machine actuelle

Les copies sous `icons/.icons/` sont **désindexées sans suppression** via
`git rm --cached`, et ignorées par Git ; elles restent disponibles via
`~/.icons -> ~/.dotfiles/icons/.icons`. Ce changement réduit le poids et
le nombre de fichiers des *nouveaux clones*, mais **ne récupère pas 1,3 Go
sur le disque actuel**. Déplacer ou effacer les copies locales suppose
d'avoir testé visuellement GTK, QuickShell et les thèmes non packagés.

Les objets des anciens commits restent dans l'historique de Git ; aucune
réécriture d'historique ni publication forcée n'est entreprise.
