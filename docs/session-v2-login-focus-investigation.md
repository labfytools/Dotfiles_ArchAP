# Premier login V2 — investigation isolée du 17 octobre 2026

Cette page conserve l'investigation précédente et son état BLOCKED historique.
La suite [phase 0 prewarm et focus final](session-v2-prewarm-private-validation.md)
implémente la préparation avant transaction autorisée par le nouveau ticket,
sans relaxer Recovery. La [reproduction précédente du refus naturel](session-v2-login-focus-private-validation.md)
reste disponible ; ses résultats précèdent ce changement.

## Résultat et portée

**BLOCKED pour une restauration automatique prouvée du premier login.** La cause
initiale du journal réel fourni ne peut pas être reconstruite à partir de son
observation tardive. Le patch est conservateur : il préserve le premier écart
observé, bloque aussi les mutations prédites neutres après conflit et vérifie
l'identité runtime à la réadmission. Il ne transforme pas un mapping admis en
preuve de provenance du focus. Ne pas présenter ce patch comme une résolution
du login ou le déployer automatiquement.

Travail limité à `/tmp/labfy-session-v2-real-focus-PFRt9hSW`, état Git initial
sans modification. Aucun fichier réel du journal n'a été recherché. Les données
réelles ci-dessous viennent exclusivement du ticket. Aucun client utilisateur,
autostart, catalogue Limusic, service, socket graphique utilisateur ou journal
RECOVERY_REQUIRED utilisateur n'a été modifié. Aucun commit/push.

## Faits, hypothèse et chaîne d'exécution

Le checkpoint fourni contient Firefox/Kitty horizontalement en 1, Limusic seul
en 10 et `focus=None`. Au login, `focus_origin={con_id:null,workspace:"1"}` est
une preuve de workspace explicite, différente d'un focus indisponible
`{con_id:null,workspace:null}`. Les trois clients sont observés, trois ancres
créées/nettoyées, aucune permutation effectuée. Le cleanup a pu écraser le
premier écart : la transition Limusic5 → Firefox13 associée à `kill` de l'ancre8
ne prouve donc pas le déclencheur initial.

Ordre effectif des sources de cette copie :

1. `Executor.apply` vérifie deux arbres et la session, prend le lock local,
   puis `_apply` fait preflight, crée Recovery et la baseline. Le lock ne
   verrouille ni l'input utilisateur, ni les autres clients IPC.
2. `Anchors.__init__` lance le helper GTK, sans encore créer de fenêtre.
   `Guard` découvre/suspend autotiling avant de répondre ready. Cela ne constitue
   pas une barrière générale du compositeur ni des autres processus.
3. `stage_node` admet les clients existants puis émet leur déplacement via
   `RecordedSway` → `Recovery.command`. Pour le scénario fourni, **la première
   mutation d'un client est le déplacement de Limusic existant de 10 au stage**.
   Le cas d'un client déjà actif peut changer le focus à cet instant ; aucune
   nouvelle application n'est encore lancée. Déplacer le dernier client peut
   aussi faire disparaître le workspace 10 et compliquer le recovery ultérieur.
4. `Anchors.build` sélectionne les workspaces et outputs par IPC journalisé,
   puis écrit `create` sur le stdin du helper. **La première création d'ancre
   est la première admission de nouvelle surface susceptible de prendre le
   focus sans passer par `RecordedSway.command`**. Les `focus`/`layout` suivants
   sont journalisés. L'exception existante `anchor_owned` utilise PID/pidfd et
   identités exactes du helper ; ce n'est pas une preuve de cause de l'input.
5. L'executor sélectionne le stage puis appelle `launch`. Les Popen sont
   séquentiels, leurs mappings sont asynchrones : ordre de lancement différent
   d'ordre de mapping. Limusic reçoit toujours zéro lancement. Les autres
   clients peuvent prendre le focus pendant l'attente des cardinalités.
6. Les groupes sont constitués par app_id. Le provider Firefox résout les UUID
   **avant** l'admission Recovery des nouveaux clients. `capture/resolve` lit
   l'arbre et publie une requête runtime ; le companion change `titlePreface`,
   sans demander `focused:true`. Le native host ne commande pas Sway. Une UUID
   exacte ne prouve pas qui a changé le focus pendant l'attente du provider.
7. La boucle `captured` admet les identités puis stage les clients non présents
   dans le stage. La première commande suivante peut constater le focus modifié.
   Avant le patch, même en conflit, une commande prédite sans changement de focus
   pouvait partir ; le refus sur une permutation ou un workspace était tardif.
   Le guard nettoie ses ancres et relit Recovery, puis l'executor relit à son
   tour Recovery. Plusieurs observateurs pouvaient remplacer le même diagnostic.

**Hypothèse plausible, non prouvée pour le login :** un map de nouveau client ou
une transition liée aux ancres explique le premier écart, particulièrement avec
un workspace initial sans feuille. Le nombre de fenêtres ou l'absence de swap
ne suffit pas à discriminer un map, un input, un helper ou une commande IPC.

## Garanties et limites externes

Le [manuel IPC Sway](https://man.archlinux.org/man/sway-ipc.7.en) décrit les
réponses de commande, GET_TREE et les événements de fenêtre. Les informations
`focused`, `focus`, `id`, `pid` décrivent l'état, pas une autorité causale de
transaction. Ni GET_TREE suivi de RUN_COMMAND ni une souscription aux événements
ne fournissent un compare-and-swap atomique du focus avec preuve de sa cause.
Un `tick` peut aider à ordonner les observations ; il n'exclut pas l'input.

Dans [Sway 1.11, view.c, should_focus/view_map](https://github.com/swaywm/sway/blob/1.11/sway/tree/view.c),
une surface mappée dans l'espace actif peut recevoir le focus. Le premier client
d'un espace vide peut même contourner `no_focus`. C'est un mécanisme plausible,
pas la preuve du comportement exact du SwayFX installé (0.6, basé sur 1.12.0).
Une règle globale `no_focus [app_id=...]` ne constitue donc pas la correction.

Le [protocole layer-shell](https://wayland.app/protocols/wlr-layer-shell-unstable-v1#zwlr_layer_surface_v1:enum:keyboard_interactivity)
distingue absence d'intérêt clavier, exclusivité et activation à la demande ;
l'interactivité est appliquée au commit de surface. Deux observations QML de
retrait ne constituent pas une barrière Sway ni la garantie qu'aucune autre
layer ne réapparaisse. Le focus workspace explicitement validé ne doit pas être
remplacé par une feuille tirée de la pile inactive.

[Autotiling amont](https://github.com/nwg-piotr/autotiling/blob/master/autotiling/main.py)
réagit aux événements IPC et émet des commandes de split. La suspension vérifiée
des helpers connus est utile ; elle n'annule pas une commande déjà soumise et
n'empêche pas le démarrage d'une nouvelle instance après découverte. Aucun de
ces mécanismes n'établit l'origine d'un changement de focus du lot restauré.

## Patch et régressions

`Recovery.record_focus_conflict` publie dès le premier constat et conserve cette
observation avec `setdefault` ; les chemins avant/après commande, refus de
préservation et entrée recovery l'utilisent. La phase indique où l'écart a été
**observé**, pas son événement causal. Les anciens journaux restent lisibles,
sans migration ni réécriture de leur observation historique ; ce qui a été
écrasé ne peut pas être retrouvé rétroactivement.

Après `focus_conflict`, `check_focus_preservation` refuse toute nouvelle commande
mutante du journal, même prédite neutre. Cela peut laisser davantage de clients
au stage qu'auparavant : le recovery partiel n'est plus un moyen de continuer
après une ambiguïté. Le guard conserve la responsabilité d'arrêter son propre
helper et de reprendre ses helpers suspendus ; il ne tue jamais les clients.

`admit` vérifie désormais session, con_id, PID, app_id et starttime aussi lors
d'une réadmission. L'origine épinglée ne change jamais. Cette vérification ne
résout **pas** la première admission par app_id ni l'intervalle entre lecture et
commande IPC ; aucune permission de focus ou de déplacement n'est ajoutée.

Les régressions inertes couvrent workspace sans feuille, mapping tardif de
Firefox/Kitty après stage de Limusic existant, refus sans nouvel IPC, préservation
du premier écart malgré cleanup/relecture, changement de session/PID/starttime/
app_id, faux app_id d'ancre et mutation neutre après focus tiers. Les tests
existants couvrent également le crash mid-IPC avec intention pending. La
simulation des postconditions utilise le prédicteur existant : ce n'est pas
une vérification indépendante des règles du compositeur.

## Validation et reproduction proposée sur l'hôte

Résultats locaux : **23 tests focus/recovery, 27 tests backend, 12 scénarios QML
PySide6 et 5 contrôles QtTest passent**. La validation du schéma de la nouvelle
fixture et `git diff --check` passent également. Le runner QML doit être celui
de Qt6 (`/usr/lib/qt6/bin/qmltestrunner`) ; le lanceur générique a échoué sans
sortie. Trois nouvelles régressions ont aussi été exécutées contre Recovery de
HEAD dans une copie de test : elles échouent avant patch (dont émission de la
commande interdite après focus tiers et réadmissions non vérifiées), puis passent
avec le patch.

Les preuves locales sont sous `build/real-focus-env/` (logs et `results.json`,
ainsi que `baseline-regressions.log`).
Les HOME/XDG/runtime de validation sont privés dans cette copie ; les variables
de sockets et de bus utilisateur sont retirées. Le SwayFX installé échoue avant
le démarrage du serveur : `drmGetDevices2 failed`, `Cannot create GLES2 renderer:
no DRM FD available`. Aucun résultat fonctionnel headless n'est revendiqué.

Nouvelle fixture composée `tests/session_v2/login_focus.py` : vrais
Executor/Recovery/Guard/Anchors, Limusic synthétique déjà présent en 10, Firefox
et Kitty synthétiques absents, workspace 1 sans feuille et checkpoint
`focus=None`. Elle remplace les lancements applicatifs par des surfaces GTK
possédées, et le provider par une UUID synthétique stable. Le contrôleur
focalise explicitement le nouveau client juste après map et avant retour du
lancement. L'assertion attend un refus avant le premier swap, conserve les trois
clients et vérifie l'unicité de Limusic. La découverte des helpers utilisateur
est neutralisée ; aucune validation d'autotiling réel n'en découle.

À exécuter côté hôte **dans cette copie**, avec un environnement temporaire
fourni par ce harnais (les tests ne doivent jamais hériter d'un socket réel) :

```sh
python3 -B tests/session_v2/validate_login_focus.py
```

Le harnais lance les tests Python, QML et la fixture composée. Il retourne un
code non nul si un contrôle échoue, y compris au démarrage headless ; un refus
du renderer est une validation indisponible, pas un PASS fonctionnel. Pour exécuter la
fixture seule, reprendre les variables privées et les suppressions de variables
sockets/bus définies dans ce script. La fixture crée ensuite elle-même un nouveau
Lab et utilise exclusivement son socket enfant explicite. Un autre compositeur
headless compatible peut être sélectionné par `LABFY_TEST_SWAY` absolu et
`LABFY_TEST_RENDERER=pixman`, sans remplacer le compositeur installé.

Le résultat attendu est **un refus sûr**, pas un restore réussi. Compléter ensuite
sur hôte par les variantes suivantes : focus naturel sans injection, ancre au
map, input tiers avant/après map, nouveau client concurrent de même app_id,
réapparition d'une layer, workspace10 disparu, multi-output, mort du helper,
crash avant/après IPC et réutilisation PID/starttime/con_id. Chaque variante doit
avoir un runtime neuf et garder son arbre avant/après et son premier diagnostic.
Même réussie, une telle expérience ne valide pas le vrai login.

## Stratégie testable restant bloquée

Ne pas ajouter d'exception « focus sur app_id autorisé » ou « con_id dans le lot ».
Épingler session/con_id/PID/starttime est nécessaire mais ne suffit pas à décider
si l'utilisateur a focalisé ce même client. Le PID du Popen Firefox peut aussi
être un lanceur court relayé vers un processus existant.

Une solution candidate devrait séparer découverte/mapping et mutations de
placement, avant de déplacer Limusic, puis exiger une frontière d'autorité
explicite et vérifiable : identité de chaque surface, preuve de lancement quand
applicable, et contrôle des transitions de focus sur l'autorité du compositeur.
Une trace d'événements bornée et les identités épinglées permettraient de tester
les hypothèses ; elles ne suffisent pas seules à autoriser une divergence.
Une API compositeur conditionnelle avec génération et provenance serait une
piste plus forte, hors du petit patch actuel. Une autre politique nécessiterait
un acquittement utilisateur explicite après mapping, avec un protocole séparé
et testé ; ce n'est pas implicitement autorisé par le clic initial Restaurer.

**Décision en attente :** choisir une stratégie capable de prouver cette
frontière avant toute exception. En attendant, garder les refus et les journaux.
Ni les données du ticket ni les API actuellement exploitées ne permettent de
revendiquer une réparation automatique sûre du scénario réel.

## Procédure DRY-RUN proposée pour le client déjà bloqué — non exécutée

1. Ne pas relancer restore, ne pas choisir une action qui efface le diagnostic,
   ne pas tuer/déplacer Limusic, ne pas le relancer. Préparer une inspection avec
   l'utilisateur ; aucun de ces accès à sa session n'est autorisé par ce ticket.
2. Après autorisation distincte d'inspection, conserver des copies privées des
   journal/reçu/rapport et leur empreinte avant toute action. Vérifier leurs
   transaction_id, session et stage concordants ; ne pas déduire l'appartenance
   au lot du préfixe du workspace. Relever intention, pending, recovered,
   focus_origin/expected/conflict et la première observation disponible.
3. Établir explicitement le socket et l'identité du compositeur de cette session
   (UID, chemin, device/inode/ctime utilisés pour le hash `Sway.session`). Relever
   get_tree/get_outputs/get_workspaces avec ce socket explicitement choisi.
   Comparer à la session du journal ; si elle diffère, STOP, aucune commande.
4. Pour **chaque** con_id candidat, comparer PID, `/proc/PID/stat` starttime,
   app_id et session avec origin/expected. Vérifier le PID vivant et son UID,
   ainsi que l'absence de réutilisation/ambiguïté. App_id ou titre seul ne vaut
   jamais identité. Une intention pending interdit une application mécanique
   de l'instruction suggérée dans le reçu.
5. Construire un tableau sans exécution : identité complète, état observé,
   origin, expected, workspace/output actuels, workspace/output désirés,
   flottement/géométrie, statut pending et écarts. Vérifier le contenu du stage,
   les clients tiers et l'existence des outputs actifs. Vérifier où se trouve
   l'espace10 : absent, déjà utilisé, ou déplacé d'output. Ne pas supposer que 10
   est libre ni que tout client du stage appartient à la transaction.
6. Proposer uniquement les mouvements nominativement justifiés par ce tableau,
   avec critères con_id explicitement issus de l'arbre et conditions de refus.
   Faire approuver **explicitement** par l'utilisateur ce plan précis, y compris
   une éventuelle création d'espace10, son output et un changement de focus.
   Sans cette autorisation, DRY-RUN terminé, zéro mutation.
7. Après une éventuelle autorisation future, refaire immédiatement les preuves
   session/PID/starttime/emplacement/outputs/focus avant chaque action. Tout écart
   ou concurrence annule le plan. Ne jamais faire de boucle app_id, kill client,
   lancement de Limusic, focus de feuille devinée ou rollback forcé.
8. Vérifier ensuite toutes les identités et emplacements demandés, le contenu du
   stage, les outputs, les clients tiers et le focus final convenu. Conserver
   avant/après et résultats nominatifs. Un stage encore occupé ou une preuve
   manquante reste RECOVERY_REQUIRED.
9. **Archiver seulement après ces preuves et accord explicite**, avec copies,
   empreintes, session/transaction et reçu de récupération manuelle. Ne pas
   transformer un échec en succès automatique, ni simplement supprimer le
   journal pour débloquer le bouton. Aucune de ces étapes n'a été exécutée ici.
