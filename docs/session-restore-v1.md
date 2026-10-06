# Restore Plan V1 — STEP19A

## Statut et architecture

**STEP19A DOES NOT RESTORE.**

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

Avant STEP19B, aucune attente de fenêtre, aucune commande Sway mutatrice,
aucune restauration d'état interne, aucun fallback multi-output, aucune UI
QML et aucun comportement Spatial Canvas ne sont implémentés.
