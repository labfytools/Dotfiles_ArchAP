# Labfy Greeter GTK4 V1

## Contrat

`greetd` ouvre la session PAM. Le client IPC envoie exclusivement
`["/usr/bin/uwsm", "start", "default"]` dans `start_session`, avec `env=[]`.
Le greeter GTK termine ensuite, `run-ui` demande la sortie du Sway greeter,
et `greetd` démarre alors la session authentifiée. Aucun code du greeter ne
lance Sway utilisateur ou Session Restore V2. `/etc/pam.d/greetd` reste intact.

## Fichiers

- `src/greetd_ipc.py` : trames JSON UTF-8 bornées à 64 KiB, socket Unix.
- `src/auth.py` : réponses PAM `secret`, `visible`, `info`, `error`, invites successives et nouvel essai.
- `src/accounts.py` : comptes NSS dans les limites de `/etc/login.defs`, avec saisie manuelle.
- `src/system_state.py` : batterie, rétroéclairage et dernier nom réussi.
- `src/avatar_icon.py` : lecture de la copie PNG AccountsService root-owned.
- `src/avatar_backend.py` : conversion bornée puis `SetIconFile` via D-Bus système.
- `src/labfy_greeter.py` : fenêtre GTK4 et mode `--preview`.
- `style/labfy-greeter.css` : palette Mocha/Lavender versionnée autonome.
- `config/labfy-sway.conf` : Sway greeter séparé, sans `include` utilisateur.
- `scripts/start-compositor` : environnement HOME/XDG greeter, préserve `GREETD_SOCK`.
- `scripts/run-ui` : ferme le compositor après GTK.

La palette provient de `quickshell/.config/quickshell/labfy-sway/theme/catppuccin.json`.
Le fond système `/etc/greetd/background/sway.png` est lu sans dépendance au HOME utilisateur.
La ligne `output *` fournit le fallback ; `eDP-1` reprend le mode et l'échelle de cette machine.

Quick Settings → Apparence → Avatar propose un sélecteur de PNG, JPEG ou WebP.
`python-pillow` convertit l'image en PNG carré de 256 px, après vérification
de la taille du fichier et du nombre de pixels. AccountsService publie ensuite
la copie système. Le greeter ne consulte que
`/var/lib/AccountsService/icons/<username>` : fichier régulier root-owned,
PNG de dimensions bornées. Une image absente ou invalide laisse l'icône
utilisateur par défaut. L'outil de réglage utilise la politique standard
`org.freedesktop.accounts.change-own-user-data` ; il n'installe ni sudoers ni
helper root. La page QuickShell se trouve sous Apparence → Avatar ; elle ne
versionne aucune image personnelle.

## Prévisualisation sans authentification

```sh
GDK_BACKEND=wayland python3 greetd/src/labfy_greeter.py --preview
```

Dans ce mode, le sélecteur est de démonstration, le champ et les actions sont
inactifs, le slider ne peut pas écrire et aucun `GREETD_SOCK` n'est requis.
La date utilise la locale système de `/etc/locale.conf`.

## Validation locale

```sh
python3 -m unittest discover -s greetd/tests -v
python3 -m py_compile greetd/src/*.py
sway --validate --config greetd/config/labfy-sway.conf
git diff --check
```

Pour prouver l'accès à la luminosité sans variation visible, un membre du
groupe `video` peut écrire la valeur courante dans `brightness` puis la relire.
Le test automatique n'écrit que dans un sysfs fictif temporaire.

## Installation

Depuis la copie source, avec les droits root :

```sh
sudo greetd/scripts/install.sh --prepare
sudo greetd/scripts/install.sh --activate-after-visual-approval
```

`--prepare` sauve byte-for-byte les fichiers existants sous
`/var/lib/labfy-greeter/backup/` et vérifie leur SHA-256 avant toute écriture
sous `/etc/greetd`. Il installe code, CSS et configuration Sway avec ownership
root, prépare state/cache en `greeter:greeter` et active `getty@tty2.service`.
L'installateur accepte la configuration tuigreet sauvegardée ou la
configuration Labfy déjà active ; toute autre configuration active est refusée.
La commande `--activate-after-visual-approval` remplace uniquement
`/etc/greetd/config.toml`. Elle ne redémarre jamais greetd.
`/etc/greetd/sway` reste présent jusqu'à la recette réelle réussie.

Avant logout, vérifier `systemctl is-active getty@tty2.service` et le chemin
de secours `Ctrl+Alt+F2` → connexion console. En cas d'échec, depuis tty2 :

```sh
sudo /usr/local/libexec/labfy-greeter/rollback --restart
```

Le rollback root-owned vérifie les hashes, remet `config.toml` initial,
recharge systemd et ne redémarre greetd que sur demande explicite
`--restart` depuis le TTY. Les sauvegardes restent disponibles après rollback.

## Première recette réelle

Après approbation visuelle et activation sur disque, effectuer le logout normal
QuickShell, contrôler l'interface et la luminosité sur VT1, puis authentifier.
Vérifier ensuite `loginctl`, `XDG_RUNTIME_DIR`, `systemd --user`, UWSM,
`quickshell-labfy-sway.service`, l'unicité QuickShell et du chooser Session
Restore V2, autotiling, Limusic et transparency helper. Aucun commit/push avant
cette recette complète.

Les boutons d'alimentation ne sont activés que si `org.freedesktop.login1.Manager`
retourne `yes` à `CanReboot` ou `CanPowerOff` dans le contexte greeter.
Une réponse `challenge`, `no` ou une erreur les désactive. Aucun privilège
supplémentaire n'est installé. Sur la machine validée, logind retourne
`challenge` : les boutons restent désactivés par la politique en place.

Le thème de login reste Mocha/Lavender en V1. La mise à l'échelle validée
concerne l'écran `eDP-1` ; `output *` fournit un fallback. Session Restore V2
reste indépendant du greeter : seul le démarrage UWSM lui transmet la session.
La recette et ses limites sont consignées dans `VALIDATION.md`.
