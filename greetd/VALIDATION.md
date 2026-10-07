# Recette Labfy Greeter GTK4 V1

## Gates de publication

- `USER_VISUAL_VALIDATION=PASS` ; `REAL_GREETER_LOGIN=PASS`.
- `BRIGHTNESS_VT1=PASS` ; `SESSION_RESTORE_CHOOSER_COUNT=1` ;
  `SESSION_RESTORE_V2_AFTER_GREETER=PASS` : constats utilisateur après login.
- `UWSM_SYSTEMD_SESSION_CHAIN=PASS` ; `GREETER_RUNTIME_HOME_INDEPENDENT=PASS`.
- `GREETER_PERMISSIONS=PASS` ; `RECOVERY_TTY2=READY`.
- `AUTH_SECRET_NOT_LOGGED=PASS` ; `PUBLICATION_PRIVACY_SCAN=PASS` ;
  `TESTS=PASS`.
- `POWER_ACTIONS=DISABLED_BY_POLICY`.

## Chaîne de connexion

La validation visuelle et une connexion sur le greeter réel ont été confirmées
par l'utilisateur. Le chemin observé est : greetd → PAM → Labfy Greeter →
`/usr/bin/uwsm start default` → session Wayland Sway → `systemd --user`.
Le client IPC envoie un argv fixe à `start_session` ; il ne lance pas UWSM
lui-même. Après login, aucun processus du greeter ou de son Sway temporaire
ne reste ouvert.

`loginctl` indique une session `Service=greetd`, `Type=wayland` et un
`XDG_RUNTIME_DIR` propre au compte utilisateur. Les services
`wayland-wm@sway.desktop.service` et `quickshell-labfy-sway.service` sont
actifs ; un seul processus QuickShell, autotiling, Limusic et l'aide à la
transparence sont observés selon leurs modes habituels.

L'utilisateur a constaté sur VT1 que le curseur modifie la luminosité, sans
élévation de privilège. Après un checkpoint éligible, il a observé exactement
un chooser Session Restore V2 et une restauration réussie. Aucun code
Session Restore V2 n'a été modifié pour ce greeter.

## Contrôles techniques

- Faux socket greetd : trames bornées, invites PAM `secret`, `visible`, `info`,
  `error`, plusieurs invites, erreur puis nouvel essai, `start_session` avec
  `['/usr/bin/uwsm', 'start', 'default']` uniquement.
- Secret synthétique : absent des sorties stdout/stderr capturées par le test.
- Comptes NSS, batterie absente ou présente, luminosité bornée et avatar
  facultatif : tests Python réussis.
- CSS GTK chargé sans erreur ; `qmllint`, `py_compile`, validation Sway et
  `git diff --check` réussis.
- Code, CSS, config et scripts exécutables : `root:root`, non modifiables par
  `greeter`. État/cache : `greeter:greeter` en mode `0700`.
- Runtime sans dépendance au HOME utilisateur pour code, CSS, fond, config,
  état ou authentification.

## Récupération et limites

La sauvegarde initiale et son manifeste SHA-256 restent dans
`/var/lib/labfy-greeter/backup/` et ne sont pas versionnés. Le secours
`getty@tty2.service` reste actif. Depuis `Ctrl+Alt+F2`, la commande
`sudo /usr/local/libexec/labfy-greeter/rollback --restart` restaure tuigreet.
Le `config.toml` initial sauvegardé a pour SHA-256
`6c2dc3c9e0973a87ff0fb33de05e7e5c697303aec6e5e399e3caf5577cf1096a` ;
la configuration Labfy active a pour SHA-256
`33f2b27dfffdd0a6b160ecfc9b47fb570f09fba647b0b37c276c747dbe55e9f5`.

`CanReboot` et `CanPowerOff` répondent `challenge` sous `greeter` : les boutons
sont désactivés par la politique logind actuelle. Le thème V1 est fixe
Mocha/Lavender. La sortie physique validée est `eDP-1`, avec fallback Sway
`output *` si la sortie change.
