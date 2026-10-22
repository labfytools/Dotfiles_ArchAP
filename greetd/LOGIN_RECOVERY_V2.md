# Connexion Labfy / Mosaic / QuickShell — V2

État du lot : **READY_FOR_EXPLICIT_INSTALL_APPROVAL**. Aucune installation ni
activation. Ce document complète la V1 de [SESSION_SELECTOR](SESSION_SELECTOR.md)
et conserve sa recette historique. Le greeter installé utilise encore
`uwsm start default` ; le sélecteur source V1 n'est pas installé.

## Périmètre et conservation

LAB privé 0700 : `/var/tmp/labfy-greeter-mosaic-login-v2-0dvus1y_/`.
Les journaux bruts et rc sont sous `logs/` et `results.jsonl`. Le snapshot initial,
le diff V1, ses sources et 293 081 empreintes contrôlées hors paquet greeter sont
sous `audit/`. Aucun écart de contenu/mode/propriétaire/lien n'a été trouvé hors
`greetd/`. Le dépôt Mosaic reste propre à `7216eb55`, sans modification.

V1 est reprise, sans réécrire le runtime : `src/greetd_ipc.py`, `src/auth.py`,
`src/labfy_greeter.py` et `style/labfy-greeter.css` restent byte-identiques aux
sources V1 initiales. Un test ajoute le refus Mosaic puis une nouvelle tentative
PAM Stable. `session-update.py` ajoute une relecture après publication avant de
certifier son journal, et une barrière complète de durabilité avant mutation. Les autres nouveaux fichiers sont des candidats, outils,
tests et documents sous `greetd/`, pas des services déployés par Stow.

Le source candidat du lanceur, ses wrappers/configuration de référence et le
manifeste sont sous `mosaic-login-v2/launcher/`. Seuls `session.py`,
`manifest.json` et le nouveau `quickshell-guard.py` sont destinés à publication.
Les wrappers, l'entrée desktop, la configuration Mosaic, les drop-ins existants,
le binaire CORE-C V2 et wlroots restent inchangés.

## Sélecteur et autorité PAM

| Choix visible avant saisie | Commande exacte transmise après PAM, avec `env=[]` |
| --- | --- |
| SwayFX — Stable, défaut à chaque ouverture | `["/usr/bin/uwsm", "start", "sway.desktop"]` |
| SwayFX Mosaic — Expérimental, choix explicite | `["/usr/bin/uwsm", "start", "swayfx-mosaic-test.desktop"]` |

Liste immuable ; aucune interpolation, commande libre ou exécution UWSM dans GTK.
Le compte et la sélection sont figés pour la conversation. Les contrôles sont
gelés pendant une requête ; changer compte/session entre invites annule PAM.
Un refus de lancement consomme l'authentification et ne déclenche aucun repli.
L'aperçu désactive PAM, alimentation et écriture de luminosité.

`default-id` vaut actuellement `sway.desktop`, SHA256
`7936c31cdc80c790ebb9c08f20ddd2e52f7a1fe82d46e1a44a0b395137dc141e`.
La valeur V1 « déjà Mosaic » est une observation historique antérieure ; elle
ne décrit plus l'état V2. Aucun test V2 ne modifie cette préférence réelle.
Le test `stable` utilise une préférence factice dans le LAB, sans binaire Mosaic.

## Cause attestée et correctif du lanceur

Le journal du 15 octobre 2026 à **16:50:10 +02:00** contient :
`MOSAIC REFUSÉ : Isolation swayidle/autostart non chargée`.
Le nom XDG autostart dans `systemctl --user show ... -p Conflicts` est entre
guillemets, avec les antislashs de `\x2d` doublés. `.split()` conserve ce codage ;
le test reproduit le faux négatif sur la sortie réelle, pas une chaîne inventée.

`systemd_words()` valide une grammaire bornée puis décode via `shlex.split`,
sans shell. Les échappements inconnus, tokens concaténés, contrôles et noms
invalides sont rejetés. `validate_isolation()` exige l'Id exact, `LoadState=loaded`,
les chemins exacts des deux drop-ins chargés et chaque conflit d'exclusion.
Le vrai manager chargé passe en lecture seule. Les négatifs retirent chacun des
conflits et altèrent identité, LoadState et DropInPaths. Aucune garde logind,
seat/VT, cgroup, notify, parent graphique, LD ou empreinte n'est supprimée.
Les alias Stow systemd/QuickShell sont vérifiés littéralement ; les lectures et
publications visent ensuite leurs chemins canoniques sans traverser ces liens.

## QuickShell propre à Mosaic

Source : `mosaic-login-v2/systemd/quickshell-labfy-mosaic.service`, avec son
lien `.target.wants/` relatif conservé dans le même répertoire de sources.
La cible est exactement `wayland-session@swayfx\x2dmosaic\x2dtest.desktop.target`.
`WantedBy` ne vise qu'elle ; `PartOf` et `BindsTo` attachent l'arrêt au target.
`After` et `Requisite` visent target et WM. Le WM UWSM est `Type=notify` : son
`uwsm finalize` existant exporte les sockets avant `READY=1`. Aucun `exec qs`
n'est ajouté à la configuration du compositeur. Commande :
`/usr/bin/qs -c labfy-sway --no-color`. `Restart=no`, arrêt borné à 5 secondes.

L'ExecStartPre valide les états, MainPID, cgroup, SHA du processus, mapping
wlroots, contexte logind/VT et propriété des **deux sockets** par le processus.
Un autre WM, un QuickShell existant ou un serveur de notifications fait refuser
le démarrage. Aucun `Conflicts` n'arrête QuickShell Stable pour le remplacer.
Le service Stable et son lien d'activation sont byte-identiques aux originaux.

Le manager partagé contient actuellement un SWAYSOCK ancien (PID 5630), alors
que le WM Stable réel est PID 12197. Aucun correctif de la session active n'a
été tenté. La nouvelle garde empêche précisément cette confusion sur Mosaic.

Le seul adaptateur QML est une garde dans `SessionV2Service.run()` :
`LABFY_MOSAIC_SMOKE=1`, fourni uniquement au service Mosaic, refuse les opérations
V2 avant démarrage du backend. Stable garde son comportement lorsque ce drapeau
est absent. Le candidat est isolé sous `mosaic-login-v2/quickshell/`, et n'a pas
été copié dans le QML actif. Après installation approuvée, la publication de ce
QML partagé peut provoquer sa détection/relecture par QuickShell Stable ; aucun
changement de service ni redémarrage explicite n'est déclenché par les outils.

L'audit des QML trouve un PolkitAgent et le NotificationServer existants dans
labfy-sway, ainsi que les accès Sway via l'environnement SWAYSOCK. Les adaptateurs
WiFi/Bluetooth restent ceux de Quickshell. Aucun nouveau daemon/agent ou lock
n'est introduit. L'autostart XDG, swayidle, wlsunset et les collecteurs clipboard
restent exclus par les drop-ins actuels. Session Restore V2 reste désactivé dans
le smoke Mosaic, y compris ses actions manuelles. La barre réelle, les services
D-Bus, la sortie physique et les fonctions interactives restent **NOT_RUN**.

## Matrice de validation

| Contrôle | Résultat effectif |
| --- | --- |
| Suite V1 initiale | PASS : 19 recensés, 17 exécutés, 2 GTK ignorés |
| Suite greeter V2 complète avec Wayland explicite | PASS : 21/21, rc=0 |
| Même suite sans GTK | PASS : 19 exécutés, 2 ignorés, rc=0 |
| Suite lanceur/garde/publications/coordination V2 | PASS : 29/29, rc=0 |
| Ancien parser sur vraie propriété | Faux négatif reproduit ; nouveau parser PASS |
| Négatifs isolation, contexte, PID Stable, SHA, symlink et `stable` sans LAB | PASS dans tests réels/factices explicités |
| Deux `uwsm start -n <id>.desktop` | PASS, rc=0 ; aucune écriture ni démarrage |
| `systemd-analyze --user --generators=no verify` unité candidate | PASS, rc=0 |
| Relations WantedBy/After/Requisite/PartOf/BindsTo, source `.wants` | PASS, modèle statique ; manager privé non nécessaire |
| Qt6 qmllint avec vrais modules et copie candidate de 86 sources | rc=0 ; mêmes 17 avertissements qu'en baseline, aucun nouveau |
| AST + py_compile, pycache LAB | PASS, 18 fichiers Python |
| Aperçus GTK natifs, fenêtre seule, 1131 × 853 | PASS : Stable initial et Mosaic, aucun PAM |
| Root : erreur d'écriture, vraie mort après deux rename, reprise | PASS sur cibles factices, suite greeter |
| User : mort après chacun des six rename, rollback et idempotence | PASS sur cibles factices, six points d'interruption |
| Coordination : mort après user et après root, reprise des deux lots | PASS sur cibles factices, deux frontières |
| Barrières complètes : ordre fsync/publication, défauts outils/métadonnées/parents | PASS sur fixtures ; aucun fichier actif publié si échec |
| Garde complète PID/maps/inodes/autre QuickShell/logind | PASS sur fixture isolée et sockets factices ; aucun compositeur lancé |
| Préflight global du nouveau bundle | PASS, aucune publication active |
| Installation/rollback réels root/user, daemon-reload | NOT_RUN |
| Login VT1, Mosaic autonome, barre réelle, sortie et retour greeter | NOT_RUN |

Échecs initiaux conservés dans les logs : constructeur Selection convertissant
`None` en Path (corrigé) ; premier GTK sans WAYLAND_DISPLAY (socket identifié en
lecture seule puis fourni explicitement) ; préflight refusant le parent symlink
Stow (chemins canoniques corrigés) ; ConfigParser du test refusant deux lignes
Environment (une ligne équivalente, verify systemd passant). Aucun échec brut
n'est converti en PASS. PyGObject émet des avertissements de dépréciation asyncio.
Les captures sont `captures/preview-stable.png` et `captures/preview-mosaic.png`
dans le LAB ; la date affichée en anglais vient de la locale de cet aperçu.
Aucune qualification fullscreen/VT1 ou daily-driver Mosaic n'en découle.

## Audit final et correction bornée

L'audit final unique du snapshot **bundle-r1 reste FAIL** : un BLOCKING de
barrière de durabilité complète, et une limite NON_BLOCKING de couverture du
parcours positif `verify_process()`. Le bundle r1 est conservé et supersédé,
jamais promu en PASS rétroactivement.

La réparation ajoute les deux barrières complètes décrites ci-dessous, teste
leur ordre avant le premier rename et injecte des erreurs sur les outils,
métadonnées et parents : zéro cible changée. La fixture positive de la garde
et ses mutations maps/inodes/autre QuickShell/logind passent également.
Ces corrections appartiennent à une seule chaîne bornée après audit. La revue
bornée indépendante du delta et du bundle **r2** est **PASS**, sans finding
restant. La validation indépendante finale confirme **21/21 tests GTK greeter**
et **29/29 tests V2**, les 23 empreintes du bundle et le préflight global.
Inventaire r2 SHA256 :
`d4c1c393e5217ec583c1c1ac30b7b6c7841c659dfcd3a385325b3b0d19d8aa3d`.
Les tests de mort de processus ne constituent pas une coupure électrique réelle,
qui reste **NOT TESTED** ; la garantie de durabilité repose sur les fsync ordonnés
et les garanties du système de fichiers, pas sur une simulation de panne machine.

## Installation proposée — après approbation explicite uniquement

Le bundle courant examiné est `bundle-r2/` dans le LAB : sous-lots `root/` et
`user/`, inventaire `SHA256.json`. Ne jamais réutiliser les `.new` V1 ou les
premières préparations intermédiaires `staging/`. `prepare-login-recovery.py`
reconstruit les deux sous-lots depuis les sources courantes, copie les outils et
scelle les fichiers user dans le sous-lot root. Le préflight global vérifie
également default-id, Stable, les scripts greeter, config.toml et le couple
binaire/wlroots exact. Un changement impose nouvelle préparation/revue.

Les commandes ci-dessous sont **préparées, NON EXÉCUTÉES**. Avant de les autoriser,
examiner diff, captures, SHA et résultats. Les répertoires durables doivent être
neufs ; `mkdir` refuse de remplacer un lot déjà installé. Ne pas ouvrir une
nouvelle connexion pendant la courte publication des fichiers.

```sh
# UNIQUEMENT APRÈS APPROBATION — préparation durable sans activation
login_v2_bundle=/var/tmp/labfy-greeter-mosaic-login-v2-0dvus1y_/bundle-r2
python3 -I -B "$login_v2_bundle/root/login-recovery-update.py" check \
  "$login_v2_bundle/root" "$login_v2_bundle/user"
mkdir -p -m 0700 /home/fy59/.local/state/labfy-greeter-mosaic-login-v2
mkdir -m 0700 /home/fy59/.local/state/labfy-greeter-mosaic-login-v2/v2
install -m 0600 "$login_v2_bundle/user/"* \
  /home/fy59/.local/state/labfy-greeter-mosaic-login-v2/v2/
sudo mkdir -m 0700 /var/lib/labfy-greeter/login-recovery-v2
sudo install -o root -g root -m 0600 "$login_v2_bundle/root/"* \
  /var/lib/labfy-greeter/login-recovery-v2/
sudo python3 -I -B /var/lib/labfy-greeter/login-recovery-v2/login-recovery-update.py check
# Commande de publication complète, seulement après accord explicite :
sudo python3 -I -B /var/lib/labfy-greeter/login-recovery-v2/login-recovery-update.py apply
# Toujours après approbation ; recharge seulement, sans démarrer de service :
systemctl --user daemon-reload
```

Le lot user publie trois fichiers lanceur, le service et son lien dédié, et le
seul adaptateur QML canonique. Le lot root publie ensuite les quatre fichiers
V1 autorisés. Les deux bundles complets sont synchronisés avant toute mutation : sauvegardes,
manifestes, outils autonomes, coordinateur, seals/protected et journaux existants,
puis bundle et chaque ancêtre jusqu’à `/`. Le coordinateur exécute la barrière
user sous UID/verrou user avant son premier journal global. Une erreur de cette
barrière interdit toute publication et ne déclenche aucun rollback mutateur.
Les transactions autonomes possèdent également leur barrière. Verrou root
global, verrou user et journaux permettent la reprise. Chaque fichier est publié
par rename puis relu ; le lot multi-fichiers n'est pas une opération atomique
unique. Une erreur ordinaire restaure les deux sous-lots dans l'ordre inverse ;
si une restauration est empêchée, les deux sont tentées et le journal reste
`rolling-back`. Après arrêt brutal, le prochain apply restaure et s'arrête pour
vérification/nouvel essai. Aucun outil ne recharge/redémarre greetd, ne ferme une
session ou ne démarre UWSM/QuickShell. Conserver les copies durables jusqu'à
validation physique puis décision explicite de suppression ; le LAB peut alors
être archivé séparément. Une panne peut laisser un temporaire caché dans une
cible ; il n'est jamais un module chargé et exige inspection avant suppression.

## Premier essai et secours indépendant

Après installation approuvée : sauvegarder le travail, fermer volontairement
SwayFX au moment choisi, retrouver Labfy, garder Stable ou choisir explicitement
Mosaic avant le mot de passe. L'essai attendu est Mosaic autonome + QuickShell
+ Kitty de récupération. Vérifier alors barre, notifications, identité des
sockets, puis quitter Mosaic avec Super+Shift+E et choisir Stable sur Labfy.
Ce parcours complet est **NOT_RUN**. Ne pas verrouiller l'écran pendant ce smoke.

En cas de panne : Ctrl+Alt+F2, login console. Après fermeture de la session
graphique défaillante, un retour Stable explicite ne dépend ni du launcher
Mosaic ni de la préférence ni d'un ancien socket :

```sh
# Procédure manuelle APRÈS approbation, depuis console sans parent graphique :
exec /usr/bin/uwsm start sway.desktop
```

Si les fichiers publiés doivent être restaurés, depuis TTY2 et sans nouvelle
connexion concurrente :

```sh
sudo python3 -I -B /var/lib/labfy-greeter/login-recovery-v2/login-recovery-update.py rollback
systemctl --user daemon-reload
```

Le rollback n'exige ni binaire/LAB Mosaic ni IPC, et ne change pas default-id.
Si le sous-lot utilisateur est divergent/inaccessible, le secours greeter reste
indépendant :

```sh
sudo python3 -I -B /var/lib/labfy-greeter/login-recovery-v2/session-update.py \
  rollback /var/lib/labfy-greeter/login-recovery-v2
# Restauration user indépendante, sans importer le lanceur Mosaic :
python3 -I -B /home/fy59/.local/state/labfy-greeter-mosaic-login-v2/v2/mosaic-user-update.py \
  rollback /home/fy59/.local/state/labfy-greeter-mosaic-login-v2/v2
```

L'ancien greeter restauré utilise `start default` ; pour un secours indépendant
de cette préférence, utiliser la commande Stable explicite ci-dessus. Aucun
redémarrage greetd ou du PC n'est automatique ; une action de récupération
supplémentaire doit être décidée par l'utilisateur. Aucun secours ne dépend
du dépôt source ou de `/var/tmp` après promotion durable.

Aucun commit/push. Aucune modification du dépôt Mosaic, du moteur, PAM, config
Sway Stable, unité QuickShell Stable ou préférence UWSM. Le candidat temporaire
CORE-C V2 reste expérimental et refuse son lancement si sa copie disparaît.
