# Documentation ArchASP Dotfiles

Cet index répartit la documentation par responsabilité. Le `README.md` racine
est la page d'accueil ; les pages ci-dessous portent les procédures et les
limites détaillées.

## Commencer ici

| Document | Responsabilité |
| --- | --- |
| [Architecture](architecture.md) | Séparation `arch-system` / dotfiles, contrat Stow et frontières de propriété |
| [Installation](installation.md) | Déploiement depuis un clone neuf et contrôles associés |
| [Recovery](recovery.md) | Reconstruction complète après perte de la machine |

## Environnement utilisateur

| Document | Responsabilité |
| --- | --- |
| [Desktop](desktop.md) | Session greetd/UWSM/Sway et composants Wayland canoniques |
| [Shell](shell.md) | Zsh, outils interactifs, plugins et scripts utilisateur |
| [systemd](systemd.md) | Limite système/user, unités et activations utilisateur |

## Inventaires et sécurité

| Document | Responsabilité |
| --- | --- |
| [Packages](packages.md) | Snapshots Pacman/AUR, services et dépendances externes |
| [Security](security.md) | Données interdites dans Git et règles de contrôle |

## Règle de propriété

Une information détaillée possède une page principale. Le README racine la
résume et pointe vers cette page ; il ne doit pas recopier l'intégralité des
procédures. Les fichiers de `.assets/` sont des inventaires factuels, pas une
deuxième documentation normative ni un installateur.

## Portée de la version 0.1.0

`0.1.0` est le snapshot stable de la première version nettoyée, documentée et
publiée. `main` demeure la branche de développement. La documentation décrit
l'état de ce snapshot ; toute évolution ultérieure doit être portée par
`main` avant une éventuelle nouvelle branche stable.
