# Recovery — reconstruire ArchASP

> **Question :** mon SSD meurt aujourd'hui. Comment reconstruire ArchASP ?

Les deux dépôts reconstruisent la configuration déclarative, pas l'intégralité
des données personnelles. Une sauvegarde séparée reste indispensable pour les
secrets, bases, documents et états applicatifs.

## 1. Installer un Arch Linux minimal

Créer le système de fichiers, installer le système de base et obtenir un
environnement démarrable avec réseau. Cette phase ne relève pas de
`Dotfiles_ArchAP`.

## 2. Restaurer `arch-system`

Cloner le dépôt système et suivre sa procédure pour le boot, le stockage, le
réseau, les paquets fondamentaux, `/etc`, greetd, les services système et les
helpers root. Ne pas copier simplement `.assets/greetd/config.toml` sans suivre
le contrat système.

## 3. Restaurer `Dotfiles_ArchAP`

Cloner l'upstream Forgejo ou, s'il est indisponible, le miroir GitHub :

```bash
git clone --recurse-submodules \
  https://github.com/labfytools/Dotfiles_ArchAP.git \
  "$HOME/.dotfiles"
cd "$HOME/.dotfiles"
git switch 0.1.0
git submodule update --init --recursive
```

La branche `0.1.0` donne le snapshot stable ; `main` est la branche de
développement.

## 4. Restaurer les paquets officiels

Comparer `.assets/pkglist-pacman.txt` avec le socle déjà installé par
`arch-system`. Installer uniquement les entrées encore pertinentes et éviter
de transformer une capture historique en commande aveugle.

## 5. Restaurer les paquets AUR/foreign

Examiner chaque entrée de `.assets/pkglist-aur.txt`, retrouver sa source et la
reconstruire avec un processus AUR maîtrisé. Les paquets locaux ou disparus
exigent une décision spécifique ; aucun helper AUR n'est supposé magique.

## 6. Déployer Stow

Suivre le [guide d'installation](installation.md) : définir explicitement les
31 packages, exécuter le dry-run, résoudre les conflits, puis seulement lancer
le déploiement réel. `docs/` et `.assets/` ne sont pas déployés.

## 7. Restaurer les services

- recharger et vérifier `systemd --user` ;
- confirmer les liens d'activation versionnés ;
- ne démarrer les unités de projets externes qu'après restauration de leurs
  exécutables et configurations ;
- restaurer les services système à partir d'`arch-system`, en utilisant les
  snapshots `.assets/enabled-*.txt` comme contrôle croisé.

## 8. Restaurer les projets externes

Cloner ou reconstruire les projets et outils listés dans
[`external-tools.md`](../.assets/external-tools.md), notamment Trainlog,
Lardon, Arch Sentinel et les outils 3D locaux. Recréer leurs builds et liens
utilisateur selon leurs propres instructions. Le dépôt de dotfiles ne contient
pas leur code.

## 9. Restaurer les secrets et données

Depuis une sauvegarde chiffrée et hors Git, restaurer selon le besoin :

- identités SSH et GPG ;
- clé et store Atuin locaux ;
- credentials Rclone, GitHub CLI, Nextcloud et applications ;
- bases Trainlog et autres données applicatives ;
- documents personnels et états non reconstructibles.

Ne copier aucun de ces éléments dans le dépôt. Vérifier leurs permissions
avant de lancer les applications.

## 10. Valider

```bash
git -C "$HOME/.dotfiles" status --short
git -C "$HOME/.dotfiles" submodule status --recursive
find "$HOME" -xtype l -print
systemctl --failed
systemctl --user --failed
sway --validate --config "$HOME/.config/sway/config"
```

Contrôler ensuite le login greetd/tuigreet, le démarrage UWSM/Sway, Swaybar,
i3status-rs, les notifications, le verrouillage, le presse-papiers, Kitty et
un nouveau shell Zsh.

## Limites actuelles

Une reconstruction à partir des seuls dépôts ne restitue pas :

- secrets, historiques et bases applicatives ;
- contenu des projets sous `~/Documents` ;
- builds locaux, outils Cargo/npm et OpenMVS ;
- helpers `/usr/local` si `arch-system` ne les recrée pas encore ;
- réglages matériels spécifiques non documentés ;
- paquets AUR disparus ou devenus incompatibles.

La récupération est donc **documentée et largement reproductible**, mais pas
une image complète et autonome du disque.
