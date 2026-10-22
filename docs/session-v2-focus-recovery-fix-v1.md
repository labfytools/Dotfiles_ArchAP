# Session V2 — focus et récupération, 22 octobre 2026

## Portée et état

Patch isolé sur `fix/session-v2-focus-recovery-20261022`, worktree
`/home/fy59/Documents/Development/labfy-session-v2-focus-recovery-20261022`,
base `5aeff41d2ce8c91966ce65fd2fa3261f34f3f954`. Le dépôt principal était propre
à cette base. Aucun commit, déploiement, redémarrage ou IPC mutant sur le bureau.
Les tests utilisent des arbres inertes ou des compositeurs enfants headless privés.
Les trois journaux réels ont été lus et leurs SHA-256 vérifiés inchangés.
Le choix réel `startup.json=new` ne donne aucune autorisation de reprise.

La fausse classification d'un changement de chemin est reproduite et corrigée
pour les nouveaux journaux disposant d'une preuve de structure. L'ordre de fin
du helper d'ancres est corrigé et les frontières du watchdog sont journalisées.
**La cause historique exacte du focus Firefox → Kitty reste non démontrée.**
Ce patch ne constitue donc pas une preuve de correction définitive du login réel.
Aucune divergence n'est réinterprétée comme un succès.

## Chronologie établie de l'incident

Le rapport réel indique trois applications observées, trois slots remplis,
trois ancres créées/permutées/nettoyées, un helper suspendu/repris et l'arbre
vérifié. `final_tree_verified=true` est une étape validée, pas la preuve que
l'arbre est resté identique après reprise.

Le journal conserve `operations=18`, une dernière intention `[con_id=8] focus`,
`focus_expected={con_id:8,workspace:"1"}` et `focus_pending=false`. Dans le code
exécuté, ces deux derniers champs ne sont publiés qu'après le retour réussi de
RUN_COMMAND et une observation de focus conforme. Cela prouve une observation
de Firefox après la commande ; cela ne prouve pas l'absence d'input concurrent.

La séquence source était :

1. Verrou V2 et refus d'une récupération active/ambiguë ; prewarm des applications,
   identités/PID/starttime, puis preuve de focus stable sur deux arbres.
2. Création de Recovery et baseline, lancement du helper d'ancres sans surface,
   découverte et suspension vérifiée d'autotiling via pidfd.
3. Réadmission stricte du lot, déplacements au stage, construction des ancres,
   résolution Firefox, permutations et retrait des seules ancres possédées.
4. Vérifications de structure, identités, outputs et flottants ; choix du focus
   final depuis le checkpoint ou l'origine prouvée ; commande vers Firefox8.
5. `guard.resume()` envoie SIGCONT et attend seulement l'état non stoppé du helper.
6. `_verify()` refait notamment l'appel provider et `validate_final()`. Sa lecture
   `final-observation` constate Kitty7, enregistre la première divergence et échoue.
7. L'appel **normal** suivant à `guard.finish()` n'a donc pas encore été atteint.
   Le finally appelle ensuite finish sur erreur, puis la récupération conservatrice.

Le premier conflit `after-command/final-observation` désigne une validation,
**pas une commande focus qui aurait échoué**. La fenêtre causale est postérieure
à l'observation conforme de Firefox et antérieure à cette lecture. Elle contient
la reprise des helpers et l'attente provider. L'incident ne permet pas de choisir
entre un helper, un autre client IPC, une activation Wayland/layer ou un input
utilisateur. Il ne démontre pas un défaut du déplacement initial.

## Autotiling, Sway et interface

L'autotiling installé est lancé par `exec autotiling` dans l'autostart Sway.
Son handler `switch_splitting` traite WINDOW/MODE, relit le focus puis envoie
`splith`/`splitv` sans critère con_id. SIGCONT peut donc libérer un backlog et une
commande déjà préparée ; l'ACK actuel ne prouve aucun drainage. Le code ne demande
pas directement de focus. Les splits peuvent insérer un parent unaire ; le code
Sway de `container_split` conserve le focus de son enfant lorsqu'il était focalisé.
La seule présence d'autotiling ne démontre donc pas la transition vers Kitty.
Une restauration avec le véritable autotiling dans un Lab privé réussit avant
et après patch.

Les erreurs réelles `'NoneType' object has no attribute 'type'` sont visibles
à 06:11:58.214 et 06:11:58.390, mais aussi avant à 06:11:53.835/.836. Le handler
appelle `output_name(con)` avant de vérifier `con` : un `find_focused()` nul peut
produire précisément cette erreur. Il n'existe ni traceback ni trace de commandes
ou d'input permettant d'en déduire une commande de focus causale.

Les règles Sway du dépôt ne refocalisent pas Firefox/Kitty. Le script historique
`layout-workspace1.sh` contient des commandes focus sur d'autres identités, sans
invocation dans l'autostart examiné. L'abonné d'opacité commande l'opacité et les
bordures. Le provider Firefox change `titlePreface`, sans `focused:true` ; un
événement titre peut toutefois réveiller autotiling. L'UI retire sa layer avant
le backend et vérifie le retrait sur deux ticks ; cela ne constitue pas une
barrière atomique sur tous les clients Wayland. `startup.py` n'effectue aucun IPC
mutant et le choix `new` ne déclenche aucune reprise. Ces composants restent inchangés.

Références primaires : [IPC Sway 1.12](https://github.com/swaywm/sway/blob/1.12/sway/sway-ipc.7.scd),
[autotiling](https://github.com/nwg-piotr/autotiling/blob/master/autotiling/main.py).
Les sources locales SwayFX `sway/tree/container.c`, `sway/input/seatop_default.c`
et `sway/ipc-server.c` ont aussi été inspectées. RUN_COMMAND/GET_TREE séquentiels
ne sont pas un compare-and-swap du focus et ne fournissent pas sa provenance.

## Protocole corrigé

Après le nettoyage/vérification du layout, l'executor observe le focus,
puis appelle `guard.prepare()`. Le watchdog refuse s'il reste une ancre et
quitte son helper ; il acquitte seulement après preuve de sortie sur le pidfd.
Cela se produit pendant la suspension possédée, avant le focus final et SIGCONT.
La vérification `Anchors.owned` commence par PID/app_id : les fenêtres applicatives
peuvent être vérifiées après la sortie/récolte du helper, sans dépendre d'un zombie.
Une candidate possédée exige toujours son pidfd exact.

Le moteur contrôle le focus après prepare, émet la commande finale sous les
contrôles Recovery existants, observe avant/après resume, puis avant/après finish.
La clôture préparée ne ferme plus d'ancre et n'écrit plus de quit tardif.
Les chemins d'erreur conservent le nettoyage des seules ancres possédées et la
reprise de tous les helpers dont le watchdog possède la suspension. Un helper
initialement stoppé n'est jamais repris.

Les six observations `focus_boundaries` sont durables et bornées à huit ; elles
localisent un premier constat, sans attribuer une cause. L'intention conserve
désormais explicitement `focus_after` après réponse et observation conformes.
Toute divergence refuse la suite ; aucun rattrapage/refocus automatique n'est
ajouté. Les contrôles finaux après reprise et après finish restent présents.

**Limite :** prepare est une barrière sur le processus possédé, pas un ACK
coopératif d'autotiling. Un helper repris peut toujours commander Sway. Une
nouvelle instance non découverte, un autre client ou l'input restent concurrents.
Le patch contrôle ces divergences observables et les refuse ; il ne prétend pas
établir une causalité atomique ou empêcher tout changement après la dernière lecture.

## Récupération canonique

L'ancien `_recover` exigeait `current == expected`, chemins bruts inclus.
Il pouvait donc annoncer `IDENTITY_OR_MEMBERSHIP_CHANGED` pour `[0] → [0,0]`
ou `[1] → [1,0]`, alors que la validation finale ignorait déjà ces chemins et
contrôlait ordre/placement/layout. La reproduction inerte échoue avant patch
avec exactement deux rejets Firefox/Kitty, puis passe après correction.

Les nouveaux journaux V1 contiennent une extension facultative
`structure_expected`, capturée sur l'arbre confirmé après commande. Elle utilise
la même normalisation qu'Anchors : seuls les splits unaires splith/splitv/none
sont contractés. Les feuilles sont les vrais con_id ; branches ordonnées,
layouts tabbed/stacked et appartenance aux workspaces restent significatifs.
La preuve est bornée en profondeur, nombre de branches et workspaces et soumise
à la limite durable JSON existante. Aucune version de Project DB n'est concernée.

Avant de réconcilier des chemins, Recovery exige :

- Même session et aucune intention fenêtre/focus pending.
- Ensemble exact des fenêtres gérées et étrangères, sans admission par app_id.
- Égalité complète con_id/PID/starttime/app_id, workspace/output, flottement et
  géométrie flottante pertinente pour tout le lot.
- Égalité de la structure canonique à la preuve durable antérieure.

Un changement de branche/layout/ordre reste refusé même si les chemins bruts
n'ont pas changé ; chaque commande de récupération recontrôle la structure.
Seuls les chemins `expected` sont réconciliés. Origin, before, intention et
premier conflit restent conservés ; `path_reconciliations` garde les chemins
avant/après (quatre lots maximum, puis refus plutôt qu'écrasement).
Le contrôle strict avant chaque commande relit toujours l'état exact.

Les journaux historiques restent lisibles mais **sans fabrication rétroactive de
preuve structurelle**. Une différence de chemin sans preuve devient
`PATH_EQUIVALENCE_NOT_PROVEN`, une vraie différence de placement/identité reste
`IDENTITY_OR_MEMBERSHIP_CHANGED`, une structure différente devient
`STRUCTURE_OR_ORDER_CHANGED`. Aucun journal réel n'a été réécrit.

Reconnaître sans IPC une fenêtre déjà à son origine n'efface pas le conflit de
focus : le reçu reste `RECOVERY_REQUIRED` avec `FOCUS_RECOVERY_NOT_PROVEN`.
Ce patch ne débloque donc pas automatiquement la transaction réelle déjà refusée.

## Validation et preuves

Les commandes, résultats détaillés et empreintes sont conservés dans
`build/focus-recovery/`, `build/real-focus-env/` et `build/session-v2-tests/` du
worktree. Ces artefacts sont locaux, non déployés. Commande de validation composée :

```sh
LABFY_TEST_RENDERER=pixman python -B tests/session_v2/validate_login_focus.py
```

Le runner impose HOME/XDG privés et retire les sockets/bus de la session réelle.
Chaque Lab lance SwayFX 0.6 / Sway 1.12 sur un socket enfant distinct avec Pixman.
Les applications et UUID Firefox sont synthétiques. Les injections « helper »
utilisent une commande déterministe du contrôleur après reprise ; elles ne
prétendent pas reproduire une commande focus du véritable autotiling.

Les scénarios positifs exigent success, slots/permutations complets, arbre exact,
focus hors stage, recovery complete et toutes les postconditions. Les négatifs
exigent un refus, le maintien des clients et de l'incident, et l'absence de
refocalisation. Les tests d'interruption conservent les intentions pending.
`test_bootstrap.py` utilise désormais un temporaire court pour ne pas dépasser
la limite AF_UNIX dans un worktree profond ; aucun test n'a été supprimé.

Résultats du dernier contrôle composé : **29 tests focus/recovery, 71 tests
backend, 13 tests QML Python, 5 contrôles QtTest et 15 scénarios de login headless**.
Les cinq variantes de `path_stability_runtime.py` et les dix variantes de
`crashes.py` passent également. Les scénarios de succès exigent toutes les
postconditions ; les injections tardives exigent RECOVERY_FOCUS_MISMATCH après
les trois swaps, sans refocalisation.

Un élargissement à `runtime.py` a validé les 28 permutations de layouts ainsi
que les cas de performance/multi-workspace précédant le flottant. **La suite
complète ne passe pas** : sa fixture GTK flottante repasse de 400×240 à 122×82
après le resize, d'où un refus de postcondition/état. La sonde privée identique
échoue aussi contre la baseline non modifiée (`floating-baseline.log`) ; le
patch échoue avec le même retour spontané de taille (`floating-patched.log`).
Aucune tolérance géométrique ni suppression de ce test n'a été ajoutée. Ce
résultat ne permet pas de revendiquer une validation complète des flottants ;
les contrôles continuent de refuser leur géométrie divergente. Les deux cas
d'identité après le flottant dans cette suite n'ont pas été atteints.

## Validation proposée au prochain login — autorisation humaine requise

1. Faire relire le diff ; autoriser séparément son intégration/déploiement et un
   essai réel au prochain login. Rien de cela n'a été exécuté par cette mission.
2. Conserver les journaux/empreintes de l'incident actuel. Un traitement de son
   `RECOVERY_REQUIRED` nécessite un plan nominatif et une autorisation distincte ;
   ne pas l'effacer ni utiliser le choix `new` pour le reprendre.
3. Au login autorisé, relever versions, checkpoint voulu, session/socket, outputs
   et helpers ; utiliser uniquement le choix Restaurer explicite, une seule fois.
   Pour le cas nominal, laisser les interactions se terminer avant la transaction.
4. Conserver tentative/journal/reçu, six frontières focus et arbres avant/après.
   Vérifier identité runtime de chaque fenêtre, slots/ordre/layout/outputs,
   ancres absentes, helpers repris, focus convenu hors stage et recovery complete.
5. En cas d'écart, arrêter l'essai et conserver son premier constat. Ne pas
   cliquer Réessayer en boucle, refocaliser via script, relancer apply ou supprimer
   RECOVERY_REQUIRED. Comparer les frontières et compléter par une trace IPC/input
   explicitement autorisée pour discriminer les causes restantes.
6. Un essai séparé avec interaction volontaire doit conserver le focus extérieur
   et refuser toute mutation après le conflit observable ; il demande lui aussi
   une autorisation explicite. Un résultat headless ne valide pas le login physique.
