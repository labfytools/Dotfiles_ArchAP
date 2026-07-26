# Dotfiles ArchASP

Configurations utilisateur de mon poste principal sous **Arch Linux**, avec un environnement **Wayland / Sway**.

Ce dépôt contient uniquement les fichiers liés à ma session utilisateur.  
Les configurations système, les paquets, Btrfs, Snapper, Limine, TLP, nftables et les outils nécessitant les droits root sont gérés séparément dans le dépôt [`arch-system`](https://git.labfytools.com/fy59/arch-system).

## Environnement

- Arch Linux
- Sway
- Wayland
- Kitty
- Zsh
- Neovim
- PipeWire / WirePlumber
- systemd utilisateur
- GNU Stow pour le déploiement des fichiers

## Contenu

Le dépôt regroupe notamment :

```text
.config/
├── kitty/
├── nvim/
├── sway/
├── systemd/user/
└── ...

.local/
├── bin/
└── share/

.zshrc
```

### Scripts utilisateur

Le dossier `~/.local/bin` contient plusieurs outils personnels, notamment :

- gestion temporaire du seuil de charge de la batterie ;
- synchronisation Nextcloud à la demande ;
- lancement conjoint de Thunderbird et Proton Mail Bridge ;
- démarrage et arrêt à la demande de VMware et Samba ;
- notifications de batterie faible ;
- outils de maintenance Arch et AUR ;
- scripts liés à Sway, au presse-papiers et à la session Wayland.

### Services systemd utilisateur

Les unités présentes dans `.config/systemd/user/` permettent notamment de gérer :

- les notifications de batterie ;
- Cliphist ;
- GNOME Keyring ;
- l’agent SSH ;
- Swayidle ;
- Wlsunset ;
- Proton Mail Bridge ;
- différents services propres à la session graphique.

Les services lourds ou occasionnels ne sont pas démarrés en permanence.

## Installation

Cloner le dépôt dans le dossier personnel :

```bash
git clone \
    https://git.labfytools.com/fy59/Dotfiles_ArchAP.git \
    "$HOME/Dotfiles_ArchAP"

cd "$HOME/Dotfiles_ArchAP"
```

Avant tout déploiement, vérifier les liens qui seraient créés :

```bash
stow --no --verbose --target="$HOME" .
```

Puis appliquer les dotfiles :

```bash
stow --verbose --target="$HOME" .
```

En cas de conflit avec des fichiers existants, les sauvegarder ou les comparer avant de les remplacer.

## Recharger la configuration

Après une modification des unités systemd utilisateur :

```bash
systemctl --user daemon-reload
```

Pour réactiver les unités voulues :

```bash
systemctl --user enable --now NOM.service
systemctl --user enable --now NOM.timer
```

Pour recharger Sway :

```bash
swaymsg reload
```

## Mise à jour du dépôt

Depuis le dépôt :

```bash
git status
git add -A
git commit -m "chore: update user configuration"
git push
```

Les données sensibles ne doivent jamais être ajoutées au dépôt.

Sont notamment exclus :

- clés SSH ;
- mots de passe ;
- jetons d’accès ;
- fichiers `.netrc` ;
- mots de passe d’application ;
- clés WireGuard ;
- bases de données personnelles ;
- fichiers contenant des informations privées.

## Séparation avec `arch-system`

| Dépôt | Responsabilité |
|---|---|
| [`Dotfiles_ArchAP`](https://git.labfytools.com/fy59/Dotfiles_ArchAP) | Configuration utilisateur, Sway, Neovim, Kitty, Zsh, scripts et unités systemd utilisateur |
| [`arch-system`](https://git.labfytools.com/fy59/arch-system) | Paquets, configuration système, Btrfs, Snapper, Limine, TLP, nftables, sudoers et helpers root |

Cette séparation évite de mélanger les fichiers personnels avec les éléments propres à l’installation du système.

## Avertissement

Ces fichiers correspondent à mon matériel, mon utilisateur et mon organisation personnelle.

Ils peuvent servir de référence, mais ne doivent pas être déployés tels quels sur une autre machine sans vérifier :

- les chemins ;
- le nom d’utilisateur ;
- les écrans et périphériques ;
- les commandes disponibles ;
- les unités systemd ;
- les dépendances installées.

## Licence

Configuration personnelle fournie sans garantie.
