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

## Migration locale : nettoyage du 1er novembre 2026

Les thèmes ont d'abord été désindexés (`git rm --cached`) et ignorés par Git.
Au second passage, une comparaison a montré que les fichiers SVG du thème
`Tela-circle-blue` local **diffèrent** de ceux fournis par Pacman. Pour ne
pas changer les icônes GTK existantes, les deux répertoires suivants ont été
**conservés** sous `icons/.icons/` :

- `Tela-circle-blue/` : thème GTK local, environ 103 Mo ;
- `default/` : réglage local du curseur, hérite de `Bibata-Modern-Ice`.

Le lien `~/.icons -> ~/.dotfiles/icons/.icons` reste en place. QuickShell
utilise toujours le thème distinct `Tela-circle-purple-dark` installé dans
`/usr/share/icons`. Les 14 autres familles locales ont été archivées avant
leur suppression. Le dossier local est passé d'environ 1,3 Go à 103 Mo.

### Sauvegardes locales vérifiées (hors Git)

Les deux archives Zstandard et leurs manifestes SHA-256 se trouvent dans
`~/.local/share/dotfiles-archives/` :

- `icons-inactive-20261101.tar.zst` (44 Mio) : les 14 thèmes supprimés,
  266 869 entrées dans l'archive ;
- `icons-active-local-20261101.tar.zst` (2,9 Mo) : copie de sauvegarde
  des thèmes `Tela-circle-blue` et `default` toujours installés.

Pour restaurer une copie locale après l'avoir vérifiée :

```bash
cd ~/.local/share/dotfiles-archives
sha256sum -c icons-inactive-20261101.tar.zst.sha256
mkdir -p ~/.dotfiles/icons/.icons
tar -I zstd -xf icons-inactive-20261101.tar.zst -C ~/.dotfiles/icons/.icons
```

La même procédure fonctionne avec le nom de l'archive des thèmes actifs,
mais **n'écraser les fichiers en place qu'après comparaison**. Sur une
installation neuve, vérifier également l'existence du lien `~/.icons`.

Ces archives sont sur **le même SSD** : elles permettent de revenir en
arrière, mais ne protègent pas contre une perte du disque. Les copier vers
une véritable sauvegarde si une reproduction visuelle identique est voulue.
Sur Btrfs, d'anciens snapshots peuvent encore retenir des blocs supprimés.

Les objets des anciens commits restent dans l'historique Git ; aucune
réécriture d'historique ni publication forcée n'est entreprise.
