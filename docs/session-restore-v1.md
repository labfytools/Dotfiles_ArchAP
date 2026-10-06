# Restore Plan et Executor V1 — STEP19A/STEP19B/STEP19C

## Statut et architecture

**Le planner STEP19A ne restaure jamais.** L'exécution contrôlée appartient
exclusivement au module séparé STEP19B décrit à la fin de ce document.

STEP19A charge un Session Snapshot V1 persistant, observe la session Sway
actuelle avec les quatre lectures STEP18, puis produit un plan JSON. Il ne
lance ni ne tue aucun processus, ne change aucun workspace, ne déplace aucune
fenêtre et n'envoie aucune commande Sway mutatrice. L'exécuteur appartient à
STEP19B ; le Spatial Canvas appartient à STEP20.

```text
snapshot persistant validé + Session Snapshot V1 live validé
        ↓
session_restore.py (fonction pure)
        ↓
labfy.sway.restore-plan / version 1
```

Le point d'entrée reste :

```bash
session_snapshot.py plan <name>
```

`session_snapshot.py` possède le chargement sûr, le verrou partagé, la
validation persistante et la collecte IPC. `session_restore.py` ne possède ni
I/O fichier, ni subprocess, ni API Sway. Il reçoit deux documents normalisés
et réutilise donc sans duplication la classification, la résolution
DesktopEntry et l'inventaire live de STEP18.

## Enveloppe Restore Plan V1

```json
{
  "schema": "labfy.sway.restore-plan",
  "version": 1,
  "read_only": true,
  "execution_supported": false,
  "source_session": "dev",
  "source": {},
  "live": {},
  "policy": {},
  "matches": [],
  "unmatched_source_windows": [],
  "actions": [],
  "diagnostics": {}
}
```

Le planner n'ajoute pas d'heure courante. Les seuls timestamps viennent de ses
entrées. Un même couple snapshot/live produit donc le même plan.

Chaque action contient au minimum :

```text
action_id
action
phase
source_window
snapshot_identity
depends_on[]
```

`depends_on` exprime les chaînes futures, par exemple lancement, placement,
arbre puis focus. Il n'exécute pas ces opérations.

## Inventaire live et identité runtime

`live.windows[]` conserve :

```text
runtime.con_id, runtime.pid, workspace, output
app_id, class, instance, desktop_entry, executable_basename
classification.category, classification.managed_by
floating, fullscreen_mode, scratchpad, focused, title_hint
```

Les PID et `con_id` sont exposés comme observations pour un futur exécuteur
dans la session courante, mais `policy.runtime_identity_fields` est vide. Ils
ne participent jamais au matching persistant : ils changent, et peuvent même
être réutilisés numériquement, après logout ou reboot.

## Matching one-to-one

Une arête snapshot→live n'existe que si une preuve d'identité applicative
existe. Les preuves, par poids décroissant, sont :

1. même DesktopEntry résolue ;
2. même `app_id` ;
3. même classe XWayland/`StartupWMClass` ;
4. même instance ;
5. même basename exécutable compatible.

Deux `app_id` explicites et différentes interdisent un match fondé seulement
sur un basename. La résolution DesktopEntry n'est pas réimplémentée : elle
provient de `resolve_desktop_entry()` STEP18 pour le snapshot comme pour le
live.

Le workspace identique, le même état floating et un `title_hint` identique
servent seulement de départage. Un titre ne crée jamais un candidat et n'est
jamais une identité obligatoire.

Le planner trie globalement toutes les arêtes par preuve, puis applique un
matching one-to-one. Une fenêtre live ne peut satisfaire qu'une fenêtre
sauvegardée. Pour deux Firefox sauvegardées et une live, une seule est
réutilisée ; l'autre reste absente. L'ordre snapshot ne sert qu'au dernier
départage.

## Confiance

```text
exact       DesktopEntry identique + app_id ou classe identique
high        DesktopEntry, app_id ou classe exacte sans preuve combinée
medium      instance ou basename compatible
ambiguous   plusieurs arêtes de meilleur score subsistent
unresolved  aucune preuve suffisante
```

`exact` n'est jamais déduit du PID, du `con_id`, du titre seul ou de la seule
position dans l'arbre.

## Classification et lancement futur

### Applications utilisateur

Une application absente n'est proposée au lancement que si sa DesktopEntry a
été résolue avec confiance STEP18 `exact`. Une identité heuristique ou
absente produit `manual-required` ; aucune ligne de commande n'est inventée.

Le futur backend STEP19B est figé conceptuellement comme :

```json
{
  "backend": "uwsm-app-desktop-entry",
  "argv": ["uwsm", "app", "--", "firefox.desktop"],
  "execute_in_step19a": false
}
```

L'audit de `uwsm 0.27.0` confirme que `uwsm app` accepte un exécutable, un
identifiant DesktopEntry ou son chemin, et lance l'application comme scope ou
service dans une slice graphique. Sa documentation recommande ce mécanisme
pour ne pas accumuler les applications dans l'unité du compositeur. STEP19B
devra donc préférer l'identifiant DesktopEntry via `uwsm app` à `gtk-launch`,
`gio launch` ou un enfant direct de Sway. STEP19A ne l'exécute jamais.

Le lancement ne promet pas de restaurer l'état interne d'un terminal, les
onglets d'un navigateur ou le contenu propre à une application.

### Applications gérées par autostart

Une vue présente est réutilisée normalement. Une vue absente produit
`skip-autostart-managed`, jamais `launch-application`, car `sway-autostart`
possède son lancement. C'est notamment le contrat de `limusic-app` issu de
`exec limusic-app`. STEP19B devra attendre ou demander une intervention au
lieu de créer une double instance.

### Infrastructure et daemons

`session-infrastructure` et `daemon` ne produisent jamais de lancement.
QuickShell, Polkit, autotiling, wlsunset, les services systemd utilisateur et
le listener de transparence restent possédés par leur sous-système. Une
absence inattendue produit `manual-required`.

## Workspaces et outputs

Chaque action conserve `desired_workspace` et `desired_output`. Une fenêtre
live au mauvais endroit produit `reuse-window`, puis `move-to-workspace`, sans
lancement supplémentaire.

Les outputs sont appariés par nom de connecteur. La politique V1 est :

```text
connector name preferred
missing output = deferred-no-fallback
```

Si le connecteur sauvegardé est absent, le planner produit
`manual-required(reason=missing-output)` et n'invente ni écran ni fallback. Le
lancement d'une application absente est lui aussi différé dans ce cas.

## Arbre Sway natif

Le planner compare une signature sémantique par vue : layout/orientation du
workspace, chaîne des containers parents, layout/orientation/percent des
parents, branche, index et percent de la fenêtre. Les `container_id` runtime
sont exclus.

Une différence produit `restore-tree-position` avec
`capability=partially-supported`. Sway natif sait déplacer, splitter, choisir
un layout et ajuster des proportions, mais V1 ne prétend pas reconstruire
atomiquement tout arbre arbitraire. STEP19B devra valider ses primitives et
replanifier après l'apparition des fenêtres.

Seul `layout_engine=sway-native` est accepté. `spatial-canvas-v1` reste hors
périmètre jusqu'à STEP20.

## Floating, fullscreen et scratchpad

Une différence live/source produit une intention distincte :

```text
restore-floating
restore-fullscreen
restore-scratchpad-hidden
restore-scratchpad-visible
```

Une fenêtre live présente dans le scratchpad alors que le snapshot ne le
demande pas produit `manual-required`, plutôt qu'une hypothèse destructrice.

## Ordre et focus

Le focus est toujours la dernière phase. Il n'est ajouté que si le focus live
diffère ou si une intention antérieure pourrait le perturber.

```text
1. match-managed  : réutiliser/différer/bloquer
2. launch         : intentions de lancement exactes
3. wait-match     : réservé au rematching STEP19B
4. workspace      : placement workspace/output
5. tree-layout    : arbre Sway natif
6. floating
7. fullscreen
8. scratchpad
9. focus
```

Le validateur refuse une dépendance future, un recul de phase ou une action
après le focus.

## Actions V1 et refus explicites

```text
reuse-window
launch-application
skip-autostart-managed
move-to-workspace
restore-tree-position
restore-floating
restore-fullscreen
restore-scratchpad-hidden
restore-scratchpad-visible
restore-focus
manual-required
```

`manual-required` porte notamment les raisons suivantes :

```text
no-exact-launch-identity
missing-output
non-restorable-category
live-window-unexpected-scratchpad
```

Dire que l'automatisation ne sait pas est préférable à une commande inventée.

## Garanties et limites STEP19A

Le module planner n'importe pas `subprocess`, ne contient pas `swaymsg`, et ne
possède aucune fonction de lancement, d'écriture ou de suppression. Le CLI
n'appelle que :

```text
show_session(name)   # lecture et validation persistante
collect(autostart)   # quatre IPC read-only STEP18
build_restore_plan() # fonction pure
```

Le plan expose :

```text
read_only = true
execution_supported = false
mutating_commands_executed = 0
applications_launched = 0
snapshots_written = 0
```

Le planner n'effectue aucune attente de fenêtre, aucune commande Sway
mutatrice, aucune restauration d'état interne, aucun fallback multi-output,
aucune UI QML et aucun comportement Spatial Canvas.

## Executor V1 — STEP19B

### Frontière d'effets et CLI

`session_restore.py` reste le moteur pur. `session_executor.py` est la seule
frontière autorisée à ouvrir le lock d'exécution et à lancer des argv directs.

```text
Session Snapshot V1 validé
        ↓
Restore Planner pur
        ↓
Restore Plan V1 frais
        ↓
Session Executor V1
        ↓
uwsm app + Sway IPC ciblé
```

La mutation nécessite une intention explicite difficile à déclencher par
accident :

```bash
session_snapshot.py apply <name> --execute
```

`apply <name>` sans `--execute` retourne
`RESTORE_EXECUTION_REQUIRES_EXPLICIT_EXECUTE` sans charger l'exécuteur. Le CLI
n'accepte jamais un fichier Restore Plan comme autorité. Chaque apply exécute
obligatoirement :

```text
load snapshot → collect live → build fresh plan → validate → preflight → execute
```

Le snapshot est hashé avant et après l'opération. Une différence produit un
échec explicite ; l'exécuteur ne possède aucune API d'écriture de snapshot.

### Capability gate intégrale

Avant le premier lancement ou la première commande Sway, l'exécuteur examine
toutes les actions. Le sous-ensemble STEP19B est :

```text
reuse-window             no-op revalidé
launch-application       uwsm app + attente/rematching
skip-autostart-managed   no-op explicite, propriétaire inchangé
move-to-workspace        workspace numérique seulement
restore-floating         enable/disable déterministe
restore-fullscreen       modes 0 et 1 seulement
restore-focus            toujours dernière mutation
```

Ces actions bloquent l'ensemble du plan avec
`RESTORE_BLOCKED_UNSUPPORTED_ACTION` et une liste précise, sans aucune mutation :

```text
restore-tree-position
restore-scratchpad-hidden
restore-scratchpad-visible
manual-required
toute action inconnue
```

Un matching runtime `ambiguous`, un workspace non numérique et un mode
fullscreen non prouvé bloquent eux aussi le plan. Une fenêtre absente n'a pas
encore de position d'arbre observable ; le planner n'émet donc une différence
`restore-tree-position` que pour une fenêtre déjà matchée. STEP19C pourra
replanifier l'arbre après apparition.

### Lock privé

Un apply détient un `flock(LOCK_EX|LOCK_NB)` sur `.restore.lock` pendant toute
la séquence load/plan/execute/rehash. Le fichier est régulier, ouvert sans
suivre les symlinks et forcé à `0600` dans le répertoire sessions `0700`. Le
fichier peut persister ; la fermeture du FD libère le lock. Aucun daemon ou
scheduler supplémentaire n'est créé.

### DesktopEntry et lancement UWSM

`launch.argv` dans le plan reste purement descriptif et n'est jamais exécuté.
Pour chaque lancement, l'exécuteur vérifie :

```text
action = launch-application
backend = uwsm-app-desktop-entry
classification = user-application
restore_identity.confidence = exact
DesktopEntry ID syntaxiquement bornée
résolution exacte identique dans les sources XDG courantes
```

Il reconstruit ensuite lui-même exactement :

```python
["uwsm", "app", "--", desktop_entry]
```

Il n'utilise ni shell, ni `Sway exec`, ni `gtk-launch`, ni `gio launch`. Comme
`uwsm app` peut rester attaché pendant toute la vie de l'application, le
processus est lancé avec un argv direct, sorties vers `DEVNULL` et une nouvelle
session de processus. Son PID et son exit status ne prouvent jamais le succès.

### Apparition et matching post-launch

L'exécuteur conserve l'inventaire des `con_id` avant lancement, puis poll
`get_tree` via la collecte Session Snapshot V1 pendant au plus 10 secondes.
Seules les nouvelles fenêtres sont candidates. Il réutilise directement
`session_restore.match_windows()` ; il ne possède aucun second matcher.

Zéro candidate compatible conduit à `RESTORE_LAUNCH_TIMEOUT`. Plusieurs
candidates indiscernables conduisent à `RESTORE_LAUNCH_AMBIGUOUS`. Le PID du
processus lancé n'intervient pas, ce qui couvre aussi une application qui
demanderait à une instance existante de créer une nouvelle fenêtre.

### Revalidation runtime et commandes ciblées

Avant chaque mutation, une nouvelle collecte doit retrouver le même `con_id`,
une identité application compatible et un workspace connu. Cela interdit de
cibler silencieusement un `con_id` disparu ou recyclé. Après la commande, une
attente bornée à une seconde relit l'arbre jusqu'à observer la postcondition,
en revalidant l'identité à chaque lecture. Elle absorbe uniquement le délai de
visibilité IPC ; son expiration reste un échec critique.

Les workspaces exécutables sont des chaînes numériques canoniques positives.
Les noms libres restent hors périmètre afin qu'aucun quoting Sway non prouvé
ne devienne une surface d'injection. Un déplacement reconstruit uniquement :

```text
[con_id=<entier validé>] move container to workspace number <entier validé>
```

Floating utilise exclusivement `floating enable` ou `floating disable`.
L'audit de `sway(5)` 1.12.0 prouve `fullscreen enable|disable [global]` : V1
supporte `fullscreen_mode=0` avec `fullscreen disable` et le mode workspace
`fullscreen_mode=1` avec `fullscreen enable`. Le mode global et toute autre
valeur sont bloqués. Aucun état ne recourt à `toggle`.

Le focus utilise `[con_id=<id>] focus`, après la même revalidation, et reste la
dernière mutation. La disparition de la cible ne focalise jamais une autre
fenêtre par défaut.

### Rapport, arrêt et absence de rollback magique

Chaque action du rapport possède `pending`, `success`, `skipped`, `failed` ou
`blocked`, avec un `reason`. L'exécution s'arrête à la première divergence
critique et laisse les actions suivantes `pending`.

Les lancements et mutations Sway ne sont pas transactionnels. Executor V1 ne
promet aucun rollback global : sa politique est un preflight total strict,
des commandes ciblées, une vérification après chaque commande, puis un arrêt
immédiat au premier écart.

### Validation contrôlée STEP19B

La validation réelle utilise exclusivement une Kitty créée pour le test sur
un workspace numérique libre. Le scénario A réutilise la fenêtre existante et
la replace par `con_id`, sans nouveau lancement. Le scénario B ferme seulement
cette fenêtre, lance `kitty.desktop` via UWSM, observe une nouvelle fenêtre,
la rematche et la replace. Le cleanup ferme uniquement le nouveau `con_id`,
supprime uniquement le snapshot de validation et restaure le focus utilisateur
initial lorsqu'il existe encore.

Les fenêtres non marquées `TEST_ONLY` sont comparées avant/après sur
`con_id`, workspace, floating et fullscreen. L'arbre complet, le scratchpad
avancé, le Spatial Canvas et toute UI QML restent hors STEP19B.

## Tree Restore Compiler et scratchpad — STEP19C

### Audit local Sway 1.12 / SwayFX 0.6

L'implémentation STEP19C est fondée sur la documentation réellement installée
et sur des expériences `get_tree` avec des Kitty `TEST_ONLY`, pas sur une
supposition i3. La version validée est :

```text
swayfx version 0.6 (based on sway 1.12.0)
swaymsg version 0.6 (based on sway 1.12.0)
```

`sway(5)` confirme localement :

```text
layout default|splith|splitv|stacking|tabbed
split vertical|horizontal|none|toggle
focus parent|child
move left|right|up|down
move container to mark <mark>
mark --add|--replace [--toggle] <identifier>
unmark [<identifier>]
resize ... px|ppt
move container to scratchpad
scratchpad show
```

L'IPC expose le layout `stacked`, tandis que la commande correspondante est
`layout stacking`. Cette conversion est une table locale fermée. `scratchpad
show` sans critère est cyclique et n'est jamais utilisé ; STEP19C reconstruit
toujours `[con_id=<id>] scratchpad show`.

### Matrice de capacités

| Élément | Niveau STEP19C | Contrat |
|---|---|---|
| Racine `splith` | `supported-subset` | Container racine homogène, fenêtres toutes matchées |
| Racine `splitv` | `supported-subset` | Même contrat |
| Racine `tabbed` | `supported-subset` | Même contrat, layout final relu |
| Racine `stacked` | `supported-subset` | Commande locale `stacking`, layout IPC `stacked` |
| Ordre des enfants | `supported-subset` | Insertion ciblée après une fenêtre de référence |
| `H[A,V[B,C]]` et symétrique | `supported-subset` | Un seul container imbriqué, deux feuilles, splits orthogonaux |
| Arbre imbriqué arbitraire | `unsupported` | Bloqué avant mutation, jamais aplati silencieusement |
| Proportions `percent` | `unsupported` | Observées mais aucune promesse de restitution V1 |
| Branche floating | `supported-subset` | Préservée, jamais compilée comme enfant tiling |
| Scratchpad caché | `supported-subset` | `move scratchpad` ciblé + relecture V1 |
| Scratchpad visible | `supported-subset` | Workspace cible numérique déjà focalisé + show ciblé |
| Spatial Canvas | `unsupported/out-of-scope` | Aucun comportement `spatial-canvas-v1` |

Cette matrice ne signifie pas « arbitrary Sway tree restore ». Un changement
de style entre des fenêtres directement sous le workspace et un container
racine explicite, plusieurs containers imbriqués, un nesting en tête, des
splits imbriqués redondants ou un arbre live déjà imbriqué hors forme cible
sont refusés.

### Architecture et représentation normalisée

```text
Session Snapshot V1 target
        +
Session Snapshot V1 live frais
        +
matching source_window → runtime con_id
        ↓
session_tree_restore.py (pur)
        ↓
Tree Restore compilation
        ↓
operations[] typées
        ↓
session_executor.py (effets externes)
```

`TreeNode` ne conserve que `kind`, identité de fenêtre sauvegardée, layout,
percent observé et enfants. Il ne prend jamais `container_id`, `con_id` ou PID
sauvegardé comme identité persistante. Le lien live est reconstruit uniquement
depuis le matching frais du planner et le `con_id` observé dans cette session.

Le compilateur valide d'abord toutes les références V1, l'unicité des feuilles,
la branche tiling/floating, les layouts et la forme. Il compare ensuite les
arbres normalisés. Un arbre identique produit zéro opération. Pour le
sous-ensemble supporté, il produit seulement :

```text
set-container-layout
set-split-orientation
move-relative(relation=after)
```

Les opérations scratchpad sont portées par les actions du plan :

```text
move-to-scratchpad
show-scratchpad-window
```

Elles ne sont jamais des chaînes Sway provenant du snapshot. Les enums sont
validés puis traduits par l'exécuteur en argv directs, sans shell.

### Ordre et marks temporaires

`move left/right` n'est pas une primitive d'ordre universelle : sur la version
locale, elle peut extraire une vue d'un container `tabbed` ou `stacked`.
STEP19C utilise donc un mark temporaire uniquement pour `move-relative` :

```text
[reference] mark --add __labfy_restore_<token_hex_aléatoire>
[source]    move container to mark __labfy_restore_<token_hex_aléatoire>
[reference] unmark __labfy_restore_<token_hex_aléatoire>
```

Le préfixe est réservé, le suffixe contient 64 bits aléatoires encodés en hex,
et jusqu'à huit candidats sont comparés à tous les marks live avant création.
Le mark est ajouté uniquement à une fenêtre cible déjà revalidée, n'utilise
jamais `--replace`, et est supprimé dans un `finally`. Son apparition et sa
disparition sont relues. Une fuite produit `RESTORE_TEMPORARY_MARK_LEAK`.

L'ordre cible est construit en gardant le premier enfant comme ancre, puis en
insérant chaque enfant suivant après son prédécesseur cible. Cette règle est
déterministe et fonctionne indépendamment de la direction géométrique du
layout.

### Nesting supporté

Le nesting V1 supporté contient exactement un container interne de deux
fenêtres, précédé d'au moins une feuille, avec orientations orthogonales :

```text
H[A,V[B,C]]
V[A,H[B,C]]
```

Le compilateur remet d'abord l'ordre plat, applique le layout racine, crée le
split interne sur B, puis insère C après B via le mark temporaire. `get_tree`
doit ensuite être exactement égal à la topologie cible normalisée. Un arbre
plus profond ou une transition depuis un arbre live imbriqué non reconnu est
`unsupported-live-nested-tree` et bloque le plan entier.

### Proportions

Sway 1.12 expose `resize ... ppt`, mais les ajustements sont relatifs aux
frères, arrondis par la géométrie disponible et dépendants de l'ordre des
redimensionnements. Les expériences STEP19C ne justifient donc pas une
restitution générale déterministe des `percent`. Le compilateur conserve les
valeurs pour le diagnostic mais publie :

```text
percent_capability = unsupported
```

Aucune commande `resize` n'est émise et le rapport ne prétend pas restaurer
les proportions exactes ou approchées.

### Preflight global et dérive

Avant la première mutation, le capability gate vérifie toutes les actions,
les identités de lancement, les workspaces/outputs, les modes fullscreen, les
cibles scratchpad et la compilation complète d'arbre. Pour chaque workspace
compilé :

```text
toutes les fenêtres target sont matchées
aucune fenêtre tiling live inattendue n'existe
aucune fenêtre floating ne devient tiling
layout et forme sont dans le sous-ensemble
toutes les opérations sont typées et validées
aucune action manual-required ne subsiste
```

Une seule erreur rend le plan entier `RESTORE_BLOCKED_UNSUPPORTED_ACTION`
avant lancement ou mutation.

Entre deux mutations d'arbre, l'exécuteur recalcule une empreinte contenant le
layout du workspace, les parents, les layouts et l'ordre des fenêtres ciblées.
Elle doit être égale à la postcondition de l'opération précédente. Une action
utilisateur concurrente produit `RESTORE_TREE_DRIFTED` et la commande suivante
n'est pas lancée. Après chaque opération, une nouvelle empreinte doit devenir
visible ; enfin le compilateur est relancé sur le live final et doit produire
zéro opération avec une topologie target/live égale.

### Scratchpad ciblé et isolation utilisateur

Le snapshot V1 distingue :

```text
member=true, visibility=hidden, workspace=null, branch=scratchpad
member=true, visibility=visible, workspace=<numérique>, branch=floating
```

Pour une cible cachée, STEP19C exécute `move scratchpad` si la fenêtre est
hors scratchpad ou visible, puis exige la représentation cachée ci-dessus.
Pour une cible visible, une fenêtre hors scratchpad est d'abord admise, puis
`[con_id=<id>] scratchpad show` est envoyé uniquement à cette fenêtre. Le
workspace numérique cible doit déjà être focalisé au preflight ; sinon le
placement de la vue visible serait ambigu et tout le plan est bloqué.

Les autres fenêtres scratchpad, y compris celles de l'utilisateur, ne sont ni
cyclées ni marquées. Une cible disparue, une identité changée ou un matching
multiple ambigu arrête l'exécution. Cette stratégie reste sûre même avec
plusieurs membres scratchpad, car aucune commande `scratchpad show` globale
n'existe dans l'exécuteur.

### Limite non transactionnelle

Les commandes Sway restent non transactionnelles. STEP19C maximise la sûreté
par preflight intégral, revalidation avant chaque commande, postcondition après
chaque mutation, marks nettoyés et arrêt au premier écart. Il ne promet ni
rollback global, ni restauration d'un arbre arbitraire, ni reconstruction des
proportions, ni UI. `spatial-canvas-v1` demeure entièrement hors périmètre.
