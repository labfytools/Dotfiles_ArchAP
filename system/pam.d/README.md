# Politique PAM de labfy-lock

`labfy-lock` emploie la phase `auth` de PAM. Le fichier source
[`labfy-lock`](labfy-lock) reprend exactement la règle active du paquet
`swaylock` : `auth include login`. La chaîne d'authentification sur cette
installation est `login` → `system-local-login` → `system-login` →
`system-auth`. Elle conserve notamment `pam_nologin`, `pam_shells`,
`pam_faillock`, `pam_unix` et les modules standard de cette pile. Les phases
`account`, `password` et `session` ne sont pas ajoutées : `PamContext` de
QuickShell 0.3.1 utilise seulement `auth`.

Après une reconstruction du système, installer depuis la racine du dépôt :

```sh
sudo install -o root -g root -m 0644 system/pam.d/labfy-lock /etc/pam.d/labfy-lock
```

Le mot de passe d'administration se saisit uniquement dans le dialogue
normal de `sudo`. Ne pas employer Stow pour `/etc/pam.d`.

Vérifier le fichier installé avant de changer `PamContext` :

```sh
stat -c '%U:%G %a %n' /etc/pam.d/labfy-lock
cmp system/pam.d/labfy-lock /etc/pam.d/labfy-lock
test -f /etc/pam.d/login
test -f /etc/pam.d/system-local-login
test -f /etc/pam.d/system-login
test -f /etc/pam.d/system-auth
```

Après installation, régler `config: "labfy-lock"` dans le seul `PamContext`
du lockscreen, vérifier le QML et les tests, puis faire un essai réel avec
saisie du secret par l'utilisateur. Conserver le paquet `swaylock` jusqu'à
confirmation du retour au bureau. Un test synthétique ne valide pas PAM.

En cas d'échec après désinstallation du paquet, exécuter d'abord
`sudo pacman -S swaylock`, puis confirmer que `/etc/pam.d/swaylock` existe.
Remettre `config: "swaylock"`, recharger uniquement le lockscreen si
nécessaire et refaire un essai manuel. Ne pas lancer `swaylock`
par-dessus une session `WlSessionLock` déjà verrouillée.
