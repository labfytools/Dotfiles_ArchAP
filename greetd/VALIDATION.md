# Recette Labfy Greeter GTK4 V1

## Complément V2 — 15 octobre 2026

Voir [LOGIN_RECOVERY_V2.md](LOGIN_RECOVERY_V2.md) : 21 tests greeter avec GTK et
29 tests lanceur/garde/déploiement/coordination passent. Sources candidates,
bundle global et captures sont préparés ; **READY_FOR_EXPLICIT_INSTALL_APPROVAL** : audit r1 FAIL conservé, réparation de
durabilité et revue bornée indépendante r2 PASS. Aucune
installation, activation ou connexion physique. Les observations V1 ci-dessous
restent historiques, notamment la préférence alors différente.

## Sélecteur Stable / Mosaic — validation locale du 15 octobre 2026

État : **READY_FOR_USER_VISUAL_REVIEW**, changement source non activé.
La recette historique ci-dessous décrit l'ancien `start default` et ne qualifie
pas ce nouveau sélecteur. La connexion réelle du siège physique, l'approbation
visuelle humaine et les opérations root restent **NOT_RUN** pour cette version.

LAB privé `0700` : `/var/tmp/labfy-greeter-dual-session-mkzppvge/`.
`TMPDIR`, `TMP`, `TEMP`, pycache et sorties des campagnes y sont dirigés.
Les commandes exactes, rc et sorties brutes sont dans `results.json` et `logs/`.

| Contrôle | Résultat |
| --- | --- |
| Régression avant modification : unittest discover | PASS, 6 tests, rc=0 |
| `python3 -B -m unittest discover -s greetd/tests -v` | PASS, 17 exécutés, 2 GTK ignorés, rc=0 |
| Même commande avec `GDK_BACKEND=wayland LABFY_GTK_TESTS=1` | PASS, 19 exécutés, zéro ignoré, rc=0 |
| AST et py_compile, neuf fichiers Python, pycache dans le LAB | PASS, rc=0 |
| Parsing CSS par le vrai Gtk.CssProvider | PASS, zéro erreur |
| Aperçu réel dans Sway et captures natives GTK Stable/Mosaic | PASS pour 1131 × 853, rc=0 |
| Contrôle du bundle face aux quatre originaux installés | PASS, rc=0 |
| Tentative apply non-root, sans écriture | Refus attendu, rc=2 |
| Erreur d'écriture du deuxième fichier dans une cible factice | Rollback complet PASS |
| Arrêt brutal après deux vrais rename en cible factice | Reprise, rollback puis apply/rollback PASS |
| Hash/mode divergent, lien symbolique, idempotence en cible factice | PASS |
| `git diff --check` | PASS, rc=0 |
| Installation/rollback root réels, connexion physique Stable/Mosaic | NOT_RUN |
| `uwsm start -n`, lancement du launcher, seat réel | NOT_RUN |

Les tests exercent le vrai client sur socket Unix fictif : argv exacts Stable
et Mosaic, `env=[]`, défaut Stable, types/valeurs/arguments invalides, absence
de secret synthétique dans les sorties, tous les types PAM et plusieurs tours,
changement de compte/session, erreur puis nouvel essai, socket perdu à chaque
étape, lancement refusé sans repli ni réutilisation de PAM. Les vrais widgets
GTK vérifient en plus le mode preview, le gel des contrôles et le double clic.
Les tests de transaction utilisent les vraies lectures, SHA, journal, fsync et
rename dans le LAB ; seule la confiance des parents et l'UID sont adaptés à la
cible utilisateur factice. Ils ne constituent pas une installation root réelle.

La première exécution de l'aperçu a révélé six erreurs CSS `:is()` et un libellé
Mosaic tronqué. Le CSS utilise maintenant des sélecteurs GTK explicites et la
carte mesure au minimum 510 px. La capture finale et le test CSS passent ; les
sorties initiales restent dans le LAB. Les avertissements de dépréciation
Python 3.14 / PyGObject concernant asyncio sont conservés dans le log des tests
GTK ; ils ne sont pas des erreurs CSS ni des erreurs d'authentification.

Les sept modules Python et le CSS installés ont été comparés byte-à-byte aux
sources avant modification : identité complète. Les originaux sont sauvegardés
hors HOME avec SHA-256 dans le bundle et dans `installed-before.json`. Les
permissions installées sont root:root `0644`, scripts root:root `0755` ; les
répertoires config/state/cache du greeter sont greeter:greeter `0700`. Le
start-compositor installé définit HOME/XDG sous `/var/lib/labfy-greeter` et
`/var/cache/labfy-greeter`. Aucun code runtime source ne dépend de `/home/fy59`.
Aucun secret PAM réel n'est lu.

Les entrées desktop propres à chaque emplacement et le hash du binaire Mosaic
attendu sont confirmés en lecture seule. `getty@tty2.service` est actif.
`default-id` était déjà Mosaic, contrairement à l'hypothèse initiale du ticket ;
il est préservé. L'ancien greeter installé reste donc dépendant de cette
préférence jusqu'à une installation approuvée. Voir
[SESSION_SELECTOR.md](SESSION_SELECTOR.md) pour le retour Stable et la limite
du rollback qui rétablit l'ancien `start default`.

La revue finale est locale, sans revue indépendante par un autre agent.
Aucune installation, élévation, commande IPC Sway, relance de service,
modification du launcher/compositeur ou commit/push. L'aperçu est une fenêtre
Wayland ordinaire, sans changement des configurations du bureau.

## Recette historique V1 — avant le sélecteur

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
