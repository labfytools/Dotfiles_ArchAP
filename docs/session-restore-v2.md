# Session Restore V2

État de cette révision : **deux P0 de frontière prewarm/finalisation corrigés ;
validation privée Sway 1.12/Pixman ; login physique non testé pour ce patch**.
Le prewarm antérieur a été validé sur SwayFX 0.6 headless ; cette preuve
historique ne valide pas automatiquement le présent delta. Lors du premier login
du 17 octobre 2026, l’ancienne séquence a échoué avant le premier swap avec
`FOCUS_RECOVERY_NOT_PROVEN` : les trois fenêtres ont été remises à leur place
manuellement et l’incident archivé. La correction actuelle prépare les
applications manquantes avant la transaction et restaure le focus final.
Son efficacité lors d’un prochain login physique reste à vérifier.

La recette réelle réussie du **7 octobre 2026** est une preuve historique de la
révision d’alors : logout, checkpoint V2, arrêt UWSM, login, chooser unique,
arbre, focus final et identité Firefox exacte vérifiés. Elle ne valide pas les
changements de focus actuels ni le prochain login physique. Les preuves
historiques restent dans la branche locale de recherche.

## Utilisation

Le menu power conserve Verrouiller, Suspendre, Déconnexion, Redémarrer et
Éteindre. Déconnexion sauvegarde un checkpoint V2 avant `uwsm stop` ; Redémarrer
et Éteindre sauvegardent avant leur action systemd. Un échec de checkpoint
permet d’annuler ou de choisir explicitement de quitter sans sauvegarder.

Au login suivant, le chooser propose Restaurer ou Nouvelle session. Un clic
Restaurer retire sa surface et attend deux observations QML de ce retrait
(délai maximal de 1,5 seconde). Sous le verrou Session V2, le backend refuse
d’abord une récupération antérieure inachevée, puis **prépare les applications
absentes via le catalogue**, avant de déplacer une fenêtre ou de publier un
journal Recovery/Attempt. Limusic appartient exclusivement à l’autostart Sway :
elle n’est jamais lancée par Session V2, et son absence bloque la transaction.

Lorsque toutes les fenêtres attendues sont présentes, le backend vérifie les
identités, emplacements et cardinalités, puis exige une preuve stable du focus
Sway et de l’identité de session avant de reconstruire le layout. Un focus
inconnu ou ambigu (`con_id=null, workspace=null`) reste refusé sans feuille
inventée. Un focus explicitement situé sur un workspace, même sans feuille,
est une observation valide, sans preuve de la provenance d’une activation
ultérieure. Les changements de focus pendant la transaction restent refusés.

Après `DEFERRED` pour absence de focus, le dialogue reste sans capture
clavier : **activez vous-même une fenêtre ou un espace avec vos raccourcis Sway,
puis cliquez Réessayer**. Si la préparation n’a pas ouvert une application,
le dialogue conserve les fenêtres déjà lancées et propose également
**Réessayer**, sans les lancer une deuxième fois.
Le clic demande une nouvelle preuve ; il n’autorise pas un re-focus arbitraire.
Aucun retry n’est automatique. **Nouvelle session** reste disponible. Si une
autre surface exclusive conserve le clavier, il faut d’abord la libérer.
Un retrait QML expiré permet également un retry explicite sans capture clavier.

Le lot phase0 épingle les `con_id`, PID, `/proc` starttime, `app_id` et
placements runtime. Après l’initialisation de Guard/Anchors et avant le premier
move, le lot entier est relu. Chaque staging vérifie encore les membres et les
placements attendus ; ses cibles viennent exclusivement du lot épinglé. Une
fenêtre ajoutée ou remplacée après prewarm est refusée, y compris à `app_id` et
cardinalité identiques. L’origine Recovery n’est jamais redécouverte par nom
applicatif. Aucun lancement Limusic n’est ajouté.

La vérification finale relit la structure **après** les appels au provider et
**après** `guard.finish()`. Elle contrôle layout canonique, membership, sorties,
flottement/géométrie flottante, focus verrouillé et identités runtime complètes
de toutes les fenêtres gérées. Les UUID exacts du provider restent exigés.
`Recovery.complete()` refuse identité ou placement divergents, ordre relatif
modifié, focus pending/conflict et toute fenêtre pending. Executor lui fournit
le contrôle structurel sur sa dernière observation avant publication. Une
normalisation de parent unaire par Sway reste permise si placement, ordre et
layout canonique sont conservés ; les ratios exacts restent hors contrat.
Ces contrôles ne sont **pas un CAS** : ils ne garantissent rien contre une
modification postérieure à la dernière observation du compositeur.

Un succès exige le rapport final vérifié puis son acquittement durable. Après
cet acquittement ou Nouvelle session, un redémarrage QuickShell dans la même
session ne réaffiche pas le chooser. Un simple claim n’est pas un acquittement :
après redémarrage, un état DEFERRED conserve son retry explicite, un backend
encore verrouillé est observé sans relancement, et une interruption présente
le diagnostic sans restauration automatique. Une intention IPC ambiguë reste
`RECOVERY_REQUIRED` ; Réessayer ne contourne pas cette protection.

Le gestionnaire de sessions permet sauvegarde, liste, aperçu structurel,
suppression et restauration V2. L’aperçu ne modifie aucune fenêtre. Le backend
fournit aussi `show` pour inspecter une session. Les noms sont limités à 64
caractères ASCII alphanumériques, tirets et underscores, commençant par un
caractère alphanumérique. Ne pas publier les sessions ou rapports runtime.

## Installation reproductible

Prérequis : Python 3, Sway compatible, QuickShell/Qt 6, GTK3, compilateur C17,
`pkg-config`, autotiling, Kitty, Firefox et Limusic déjà configuré par l’autostart
Sway. Le catalogue est `session_v2/applications.py`. Limusic utilise
`strategy=managed-autostart`, `managed_by=sway-autostart` et aucun argv Labfy.

Depuis la racine du dépôt :

```sh
python3 -B tools/build-session-v2.py
install -Dm755 build/session-v2/labfy-v2-anchor \
  quickshell/.config/quickshell/labfy-sway/session_v2/libexec/labfy-v2-anchor
```

Le build ne déploie ni extension ni préférence. Le helper compilé et les archives
restent ignorés par Git. Déployer le package Stow `quickshell` selon le guide
habituel, puis suivre [la documentation du companion Firefox](../firefox-extension/session-v2/README.md).
Pour la correction d’identité Firefox 1.1.1, les sources locales ne suffisent
pas : une mise à jour XPI signée AMO unlisted puis une installation explicitement
autorisée sont nécessaires. Voir le companion pour le protocole de lecture seule,
l’auto-baseline uniquement après attestation native d’absence du checkpoint
automatique V2 et de toute entrée de sauvegarde nommée dans `sessions`
(échec fermé si contrôle inaccessible), les Ctrl+N automatiques après
photographie initiale, les ambiguïtés isolées et le risque résiduel
de restauration tardive indiscernable. Aucun timer ne constitue une preuve de
nouveauté ni un CAS sessionstore. Les fenêtres ambiguës observées restent refusées.
Ce delta n’a pas été validé au login physique et ne récupère pas un UUID déjà perdu.

Versions de la recette historique du 7 octobre : Firefox 157.0, SwayFX 0.6, QuickShell 0.3.1,
autotiling 1.9.4, Python 3.14.7, Qt Declarative 6.11.2 et GTK3 3.24.52.

## Architecture et invariants

`sessionui/SessionV2Service.qml` est l’unique propriétaire des commandes UI.
`Bar.qml` instancie `SessionStartupPromptV2` ; `shell.qml` désigne une seule barre
hôte. `ControlCenter.qml` utilise `SessionManagerV2` et `SessionExitGate` avec
le statut de checkpoint `saved`. Aucune surface active ne dépend du moteur V1.

Le backend capture applications, slots et structure ; il reconstruit par ancres
et swaps, puis vérifie arbre, absence d’ancres et focus final. Le guard possède
la suspension/reprise des helpers et leur récupération en cas d’interruption.
Les observations runtime ne sont pas des identités persistantes. Firefox garde
la propriété de ses fenêtres/onglets ; le companion fournit l’identité exacte.
Kitty restaure uniquement la fenêtre. Les échecs sont explicites ; aucune
approximation d’identité Firefox n’est substituée silencieusement.

Les checkpoints et sessions sont privés sous
`${XDG_STATE_HOME:-$HOME/.local/state}/labfy-sway/session-v2`. Les transactions,
locks, rapports et observations du provider restent sous `$XDG_RUNTIME_DIR`.
Les anciennes données utilisateur V1 sont conservées. `analyze-v1-migration`
est une analyse en lecture seule, sans conversion automatique ni moteur V1.
Les anciens documents V1 sont des références historiques non exécutables.

## Diagnostics et validation

```sh
python3 -B "$HOME/.config/quickshell/labfy-sway/session-v2.py" restore-status
qs ipc -c labfy-sway call sessionV2 status
systemctl --user is-active quickshell-labfy-sway.service
```

Le rapport de succès doit indiquer `status=success`, les deux vérifications
finales vraies, autant d’ancres nettoyées que créées et autant de helpers repris
que suspendus. Le diagnostic QuickShell doit retourner `backend=v2`, `busy=false`.
Le rapport backend contient des identités privées : ne pas le joindre brut à
un ticket public. Ne jamais relancer un restore pour simplement lire son statut.

Tests sur compositeur headless privé, sans logout ni accès au bureau utilisateur :

```sh
python3 -B quickshell/.config/quickshell/labfy-sway/tests/focus/test_focus.py
python3 -B quickshell/.config/quickshell/labfy-sway/tests/focus/test_qml.py
python3 -B -m unittest discover -s tests/session_v2 -p 'test_*.py'
python3 -B tests/session_v2/validate_login_focus.py
python3 -B tests/session_v2/runtime.py
python3 -B tests/session_v2/failures.py
python3 -B tests/session_v2/crashes.py
python3 -B tests/session_v2/security.py
python3 -B tests/session_v2/phase3b_runtime.py
python3 -B tests/session_v2/phase3b_ui.py
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner \
  -input tests/session_v2/qml -o -,txt
```

Les tests Python nécessitent `jsonschema` ; les scénarios UI nécessitent QuickShell
et QtTest. Les résultats synthétiques restent sous `build/session-v2-tests`,
ou dans `LABFY_SESSION_V2_EVIDENCE`. Les fixtures ne lancent que leur propre
compositeur et leurs enfants TEST_ONLY. Le build helper C17 utilise
`-Wall -Wextra -Werror`. Les métadonnées QuickShell peuvent produire des
avertissements qmllint ; le chargement réel et les scénarios Qt complètent
le contrôle syntaxique, sans prétendre à zéro avertissement.

Validation du 17 octobre dans la copie isolée : tests backend, focus et QML,
35 scénarios runtime, erreurs contrôlées, interruptions/SIGKILL, sécurité,
Limusic synthétique et scénarios QuickShell réels sur Wayland headless.
Le cas `deferred-real` maintient une seconde surface QuickShell exclusive :
focus Sway nul observé, refus sans journaux, aucun retry automatique, retrait
explicite de la surface, activation de la fenêtre tierce par le contrôleur de
test, puis demande Réessayer et succès. La fenêtre tierce retrouve son vrai
focus ; Limusic synthétique reste unique. Les fonctions des boutons sont
appelées par le harnais QML : ce n’est pas une recette de clic physique.

Le test crash mid-command tue l’executor après mutation IPC réelle mais avant
confirmation dans Recovery : l’intention durable reste pending et
`RECOVERY_REQUIRED`, sans prétendre à une récupération prouvée. Les cas Limusic
absente et dupliquée refusent sans lancement ni fermeture de Limusic. Le
catalogue et les lignes Sway `assign [app_id="limusic-app"] workspace 10` et
`exec limusic-app` restent inchangés.

Dans le bac à sable Codex, `/dev/dri` était inaccessible : le SwayFX 0.6
installé n’a pas pu initialiser son renderer GLES2. Cet échec initial ne vaut
pas un test fonctionnel. La première validation a donc utilisé Sway 1.12,
extrait du paquet local `sway-1:1.12-4-x86_64.pkg.tar.zst` dans `/tmp`, avec
Pixman, QuickShell 0.3.2 et Qt 6.12.0, sans remplacer le compositeur installé.

Après réintégration contrôlée, une deuxième validation a réussi directement
sur l’hôte ArchASP avec **SwayFX 0.6 installé**, en backend headless privé et
avec accès au renderer de l’hôte : 35 scénarios runtime, 3 erreurs contrôlées,
10 scénarios de crash, 22 contrôles de sécurité, Limusic synthétique et
7 scénarios UI QuickShell, dont `deferred-real`. Les tests backend (27),
focus (18), QML (12) et `qmllint` passent également sur les sources réintégrées.
Aucun essai n’a accédé au socket Sway de la session utilisateur.

**Nouvelle validation après la correction prewarm (17 octobre 2026).**
Une campagne sur le SwayFX 0.6 installé, mais sur un socket Wayland/Sway IPC
headless privé, a réussi les tests de focus (28), backend et prewarm (34),
QML Python (13), QtTest (5) et onze scénarios composés. Le cas nominal exécute
le véritable chemin de lancement Python `Popen` avec des applications GTK
**synthétiques** : Limusic préexiste sur 10, Kitty et Firefox arrivent sur 1
avant toute mutation du layout ; trois swaps, trois slots, arborescence
vérifiée, stage vide et focus final sur Firefox/1. Sont également vérifiés :
lancement Firefox en échec puis retry sans deuxième Kitty, focus tiers
préservé, mappings concurrents refusés et intentions IPC ambiguës conservées.

Sur le même SwayFX headless privé, les suites runtime (35 scénarios), erreurs
contrôlées (3), crash/SIGKILL (10), sécurité (22), propriété Limusic et les
sept scénarios de QuickShell passent. Les sources de production validées dans
la copie de test sont identiques octet pour octet à la version retenue pour
cette intégration. Les tests ne lancent jamais le vrai Firefox, Kitty ou
Limusic du bureau : le **prochain login réel reste non validé**, y compris
l’intégration de l’extension Firefox avec son profil habituel. Voir aussi
[l’investigation du premier échec](session-v2-login-focus-investigation.md).

Les fixtures acceptent `LABFY_TEST_SWAY=/chemin/absolu/vers/sway` et
`LABFY_TEST_RENDERER=pixman` pour une exécution sans renderer GLES2 ;
pour Qt headless utiliser `QT_QPA_PLATFORM=wayland` et
`QT_QUICK_BACKEND=software`. Elles imposent un backend headless,
un socket privé et HOME/XDG temporaires. Le répertoire de preuves, s’il est
précréé, doit avoir le mode 0700 (les JSON sont privés).

Ces résultats prouvent les chemins testés sur ce compositeur headless. Ils ne
prouvent ni le retour du focus avec tous les périphériques du bureau, ni le
comportement du prochain login SwayFX/UWSM réel. Cette validation reste à faire
séparément après réintégration contrôlée.

La campagne des corrections P0, ses résultats, les refus initiaux et les
commandes de reprise sur hôte sont détaillés dans
[la validation prewarm privée](session-v2-prewarm-private-validation.md).
Le refus DRM du SwayFX installé dans le bac à sable n’est pas un PASS SwayFX.

## Correction des chemins post-Guard du premier login

Le dernier login réel fourni au diagnostic a encore refusé après intégration
P0 : `TARGET_OBSERVATION_CHANGED`, zéro déplacement, zéro swap. Les journaux
réels restent préservés ; ils n’ont pas été recherchés ni modifiés ici.
Les chemins exacts PREWARM n’étant pas archivés, l’insertion de parents unaires
par Sway/autotiling est une hypothèse forte, pas une cause historique prouvée.

La contradiction démontrée est corrigée : après Guard, le lot courant déjà
comparé à la phase 0 devient l’observation canonique passée aux admissions.
Recovery conserve ses relectures strictes ; identité, placement, ordre et
preuve de focus ne sont pas élargis. Les chemins actualisés par les commandes
possédées sont acceptés après provider ; un changement externe pendant cette
attente reste refusé. Les protections P0 restent en place.

La campagne privée Sway 1.12/Pixman passe : 43 tests backend, suites précédentes
complètes, quatre succès de quatre slots avec parents unaires (dont un avec
autotiling enfant) et un refus post-provider ciblé. Le SwayFX/GLES2 du sandbox
échoue au démarrage faute de DRM. **Cette correction ne valide pas le login
graphique physique**, ni les applications Firefox/Kitty/Limusic réelles.
Voir le [diagnostic ciblé, les preuves et la commande hôte](session-v2-path-stability-diagnostic.md).

## Limites conservées

- Contenu et processus terminal non restaurés.
- Ratios exacts non restaurés.
- Fullscreen non pris en charge. Scratchpad pris en charge par le snapshot version 2 pour les feuilles flottantes individuelles ; les groupes restent refusés.
- Multi-output physique non validé.
- Provider Firefox candidat actuel pour le profil supporté ; plusieurs profils
  simultanés ne sont pas pris en charge.


## Snapshot version 2 — scratchpad (22 octobre 2026)

Les nouvelles captures conservent `schema=labfy.sway.session-v2` et écrivent
`version=2`. Le contrat V1 et `schema-v1.json` restent inchangés : les anciennes
sessions sont lues, validées et restaurées directement, sans conversion ni
invention d’appartenance scratchpad. `schema-v2.json` décrit la nouvelle forme ;
`schema.py` ajoute les contraintes référentielles (unicité, cardinalité, chemins,
focus et association workspace/output) aux contraintes locales du schéma JSON.
Le bundle de développement contient les deux schémas.

Dans V2, `state.scratchpad` vaut `none`, `hidden` ou `shown`. Une feuille
scratchpad est nécessairement flottante, avec son rectangle IPC entier
`x/y/width/height`. Une feuille cachée a `workspace=null` et `tree_path=[]` ;
`__i3_scratch` n’entre jamais dans les workspaces, sorties ou ancres persistés.
Une feuille montrée garde le workspace/output de visibilité. `focus` reste une
référence de slot ou null, jamais une feuille déduite d’un split. Le champ V2
`focus_workspace` conserve le workspace effectivement focalisé, y compris un
workspace vide lorsque toutes les fenêtres sont cachées. Ce seul workspace vide
est admissible sans slot ; son output doit être disponible. Une feuille cachée
ne peut être le focus persistant.

La capture inclut les scratchpads cachés sous l’output interne Sway et les
scratchpads montrés parmi les flottants normaux. Les relectures comparent aussi
app_id, PID, appartenance scratchpad et focus ; un changement donne
`SNAPSHOT_CHANGED`. Les groupes flottants/scratchpad ne sont pas aplatis en
feuilles indépendantes : ils sont refusés précisément. Les fenêtres de même
application sans fournisseur exact restent explicitement interchangeables.
Le mapping privilégie la visibilité déjà observée pour ces slots ; une feuille
scratchpad existante n’est pas exposée pour remplir arbitrairement un slot
ordinaire. Les preuves UUID/singleton restent prioritaires, puis les identités
runtime admises comprennent con_id/PID/starttime/session/placement.

La phase de placement (`plan.placements`) est distincte de la compilation des
ancres de splits. Les scratchpads existants évitent staging et `floating disable`.
Les commandes sont ciblées par l’identité admise ; `scratchpad show` n’est émis
que pour une feuille prouvée cachée et un slot explicitement montré. L’ajout
initial au scratchpad sélectionne le workspace source, même si la cible était
inactive : cette transition est prédite avant IPC. Le journal précède chaque
commande. Les transitions `floating enable` et `scratchpad show` ont une attente
bornée de 300 ms pour laisser passer la configuration Wayland initiale ; cette
attente n’est pas une preuve de stabilité. Toute divergence encore observée
reste un échec. Le rectangle intermédiaire d’un `show` peut être converti par
Sway selon l’output ; le rectangle sauvegardé est ensuite commandé et vérifié
exactement, avec appartenance, visibilité, output, layout, identité et focus.

Les nouveaux journaux Recovery sont en version 2 et suivent l’appartenance
scratchpad. Les journaux V1 restent lisibles ; une observation scratchpad absente
de leurs preuves est refusée, jamais reconstruite implicitement. Après incident,
un scratchpad déjà exactement à son origine peut être reconnu sans IPC. Si son
placement diffère, la reprise conserve les données et donne
`SCRATCHPAD_RECOVERY_REQUIRES_REVIEW` ; elle n’affiche aucune feuille pour tenter
un rollback spéculatif. Les intentions pending et les conflits de focus restent
bloquants. L’ancien journal utilisateur `RECOVERY_REQUIRED` n’est ni modifié ni
acquitté par ce patch.

Le dialogue d’échec de checkpoint montre maintenant le `reason` JSON exact,
avec une explication pour les cas connus, notamment `CAPABILITY_UNSUPPORTED`.
L’erreur conserve l’action en attente : annulation ou choix explicite de quitter
sans sauvegarder restent nécessaires. Aucun code d’erreur n’autorise le logout.

Validation et limites détaillées :
[rapport scratchpad](session-v2-scratchpad-save-and-restore-v1.md).


## Précondition Secret Service avant restauration — 22 octobre 2026

Le parcours utilisateur ajoute une barrière D-Bus indépendante du checkpoint.
Les CLI `apply-last` et `apply` exigent la collection default attendue réellement
déverrouillée ; le chooser propose son déverrouillage officiel et conserve le
clic explicite Restaurer après READY. Nouvelle session reste disponible sans
trousseau. Cette précondition ne modifie aucune postcondition de l'Executor,
aucun schéma de checkpoint/Recovery et ne résout pas automatiquement un
`RECOVERY_REQUIRED`. Une activation tardive garde les refus de focus existants.

Implémentation, audit PAM (aucun patch applicable établi), tests isolés,
installation et rollback :
[trousseau avant restauration](session-v2-keyring-before-restore-v1.md).


## ChatGPT XWayland et WhatsApp Web (27 octobre 2026)

Le catalogue ajoute deux applications précises à Firefox, Kitty et Limusic :

| Application | Identité observée | Politique |
| --- | --- | --- |
| ChatGPT | Fenêtre X11 avec WM_CLASS exactement `Chatgpt` | `single-window`, lancement `/usr/bin/chatgpt` si absent |
| WhatsApp Web | `firefox.webapp-fcd72ebe-94c5-4209-b3f6-bbaa7784cded` | `managed-autostart`, propriétaire `sway-autostart` |

L'identité X11 est une clé runtime réservée `x11-class:Chatgpt`. Elle exige un
identifiant de fenêtre X11 et une classe exacte ; un app_id Wayland ne peut pas
usurper ce préfixe. Les arbres IPC restent bruts. La classification, les
observations de récupération, le préchauffage, les swaps et les contrôles finaux
emploient la même clé, toujours avec con_id, PID et starttime. Un ancien journal
X11 sans classe ne reçoit pas rétroactivement une identité prouvée.

La capture refuse plusieurs fenêtres ChatGPT avec cette politique singleton.
Les applications absentes du catalogue restent refusées explicitement ; elles
ne sont pas retirées silencieusement de la sauvegarde. Le snapshot conserve son
format version 2 et ne contient ni commande, ni chemin de document, ni contenu
de conversation.

WhatsApp est assignée au workspace 9. La ligne d’autostart corrigée par
l’utilisateur lance directement Firefox avec `-taskbar-tab`, `-new-window` et
`-container 0`, sans intermédiaire `bash -c` et sans `-profile`.
La restauration attend cette fenêtre et ne lance pas une deuxième instance.
Le provider Firefox reste responsable des fenêtres du navigateur ordinaire.

Les tests ciblés XWayland sont dans `tests/session_v2/test_xwayland.py` et les
tests existants de préchauffage/autostart restent applicables. Le scénario
`tests/session_v2/xwayland_runtime.py` restaure deux surfaces synthétiques dans
un Sway privé : Chatgpt via XWayland et WhatsApp via Wayland. Il vérifie aussi
la préservation stricte d’une fenêtre X11 inconnue hors du lot. La capture du
bureau réel a également été contrôlée avec ChatGPT puis avec WhatsApp ouverte.
Une capture réussie ne vaut pas validation d'une déconnexion/reconnexion physique.
Un incident antérieur `RECOVERY_REQUIRED` continue de demander le traitement
nominatif décrit dans `session-v2-focus-recovery-fix-v1.md`, indépendamment de
la création d'un nouveau checkpoint.
