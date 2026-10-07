# Companion Firefox Session Restore V2

Sources de l’extension utilisée par la recette réelle validée. ID :
`session-v2@labfy.org`, version 1.0.0. Host : `org.labfy.session_v2_identity`.
Permissions limitées à `sessions` et `nativeMessaging` : aucun accès à la
navigation, aux cookies, à l’historique ou au contenu des onglets.

## Build et signature

Depuis la racine du dépôt, `python3 -B tools/build-session-v2.py` construit
`build/session-v2/labfy-session-v2-unsigned.xpi`. Le contenu du XPI est
déterministe ; le bundle backend tar.gz est seulement une sortie locale.
Aucun binaire ou XPI signé n’est versionné.

La distribution retenue est **AMO unlisted**, signée par Mozilla, puis installée
localement avec consentement explicite. Envoyer le XPI non signé via le portail
AMO de développement, choisir la distribution non répertoriée, récupérer le
package signé et l’installer depuis le gestionnaire d’extensions Firefox.
Les identifiants AMO restent hors du dépôt. Ne pas désactiver l’exigence de
signature Firefox Release. Firefox 157 est la version minimale du manifeste.

Sur le profil utilisateur validé, l’extension signée est déjà active et
`browser.startup.page=3` est déjà configuré. Le nettoyage V1 ne modifie ni
installation, ni permissions, ni préférence. Pour une nouvelle installation,
le propriétaire du profil doit choisir explicitement la réouverture des
fenêtres et onglets précédents.

## Native host

Après déploiement Stow, rendre le template `native-host.json.in` en remplaçant
`@ABSOLUTE_NATIVE_HOST_LAUNCHER@` par le chemin absolu de
`$HOME/.config/quickshell/labfy-sway/session-v2-native-host.py`.
Conserver le nom du host, le type `stdio` et l’allowlist exacte de l’extension.
Le wrapper doit rester exécutable.

Sur l’installation Linux validée, le manifeste est
`${XDG_CONFIG_HOME:-$HOME/.config}/mozilla/native-messaging-hosts/org.labfy.session_v2_identity.json`.
Le chemin historique `$HOME/.mozilla` pointe vers cette arborescence. Sur un
autre packaging Firefox, vérifier le répertoire Native Messaging utilisé avant
installation. Créer le manifeste avec permissions 0600 ; ne pas écraser un
host actif lors d’une simple mise à jour de documentation.

Le host accepte seulement le protocole `map-window` avec UUID et jeton runtime.
Les messages sont bornés à 4096 octets ; la sortie standard est réservée au
framing Native Messaging. Le host lit l’arbre Sway pour corréler le préfixe
éphémère, sans exécuter de commande Sway mutatrice. L’extension retire ce
préfixe après corrélation. Le provider exige des observations récentes et un
publisher vivant ; une identité absente ou ambiguë produit un échec explicite.

Les UUID persistants appartiennent aux fenêtres Firefox ; les observations et
identifiants de processus restent privés dans le runtime. Ne pas publier ces
fichiers. Le provider demeure le candidat validé pour le profil supporté ; le
multi-profil n’est pas pris en charge. Les fenêtres et onglets sont restaurés
par Firefox, pas par une lecture de sessionstore côté Labfy.

Voir [Session Restore V2](../../docs/session-restore-v2.md) pour le cycle complet,
les tests et les limites.
