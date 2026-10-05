# Session Snapshot V1 — STEP18A

## Objet et périmètre

STEP18A capture et valide en lecture seule l'état de session observable par
Sway. **Aucune restauration n'est implémentée.** Le collecteur ne déplace pas
de conteneur, ne change pas le focus, ne lance ni ne tue de processus et
n'écrit aucun snapshot persistant. STEP18B possédera la persistance ; STEP19,
la restauration et son interface ; STEP20, le layout spatial 2D.

Le collecteur autonome se trouve dans
`quickshell/.config/quickshell/labfy-sway/session/session_snapshot.py`. Il est
séparé de QML :

```bash
python ~/.config/quickshell/labfy-sway/session/session_snapshot.py --stdout
```

Sans `--stdout`, il refuse d'agir. Pour STEP18A, une redirection explicite vers
`/tmp` est réservée au diagnostic.

## Sources et audit de disponibilité

Les seules sources IPC sont `get_version`, `get_outputs`, `get_workspaces` et
`get_tree`. Les seules variables lues sont `XDG_CURRENT_DESKTOP`,
`XDG_SESSION_TYPE` et `DESKTOP_SESSION` lorsqu'elles existent. Le collecteur
ne lit jamais `/proc/*/environ` ni `/proc/*/cmdline`. Il peut lire le lien
`/proc/<pid>/exe`, puis ne conserve que son basename.

L'audit du 5 octobre 2026 a observé SwayFX `0.6`, fondé sur Sway `1.12.0`, en
session `wayland`, avec `XDG_CURRENT_DESKTOP=sway:wlroots:swayfx` et sans
`DESKTOP_SESSION` exporté au processus de collecte.

| Donnée IPC | Disponibilité | Volatilité | Utilité V1 | Traitement / protection |
| --- | --- | --- | --- | --- |
| output `name` | disponible | peut changer selon le connecteur | rattachement workspace et meilleur indice local | conservé ; pas supposé toujours présent au reboot |
| output `active`, `focused` | disponible | volatile | état et focus observés | conservés |
| output `rect`, `scale`, `transform`, `current_mode` | disponible | volatile | topologie multi-écran future | conservés ; refresh renommé `refresh_millihz` |
| output make/model/serial | disponible | relativement stable mais privé et parfois faux | non nécessaire au contrat actuel | exclus |
| workspace `name`, `num`, `output` | disponible | nom/output modifiables | identité locale et rattachement | conservés |
| workspace `focused`, `visible`, `urgent`, `rect` | disponible | volatile | restitution future et diagnostic | conservés |
| ordre workspace | disponible par l'ordre IPC | volatile | ordre réel observé | `order` explicite, à partir de zéro |
| container `layout`, `orientation` | disponible | volatile | reconstruction `splith`, `splitv`, `tabbed`, `stacked` | conservés |
| container ordre, parent/enfants, `floating_nodes` | disponible | volatile | structure indispensable | normalisés en références ordonnées |
| container `percent` | disponible, parfois `null` | volatile | proportions relatives | conservé |
| `rect` | disponible | volatile | géométrie effective, surtout floating | conservé |
| `deco_rect`, `window_rect`, `geometry` | disponibles | volatiles | redondants ou décoratifs pour V1 | exclus ; `rect` et `percent` suffisent au contrat actuel |
| `focus`, `focused` | disponibles | volatile | chaîne de focus observée | focus final normalisé ; listes runtime brutes exclues |
| `fullscreen_mode` | disponible | volatile | restauration future | conservé sur chaque fenêtre |
| `urgent`, `marks` | disponibles | volatiles | état utilisateur et correspondance possible | conservés |
| `app_id` | disponible pour Wayland | peut évoluer entre versions | indice d'identité principal | conservé sans le déclarer universellement stable |
| `window_properties.class/instance` | disponible pour XWayland | peut évoluer | identité XWayland | seuls `class` et `instance` sont conservés |
| `pid`, `con_id` | disponibles | strictement runtime | diagnostic de capture seulement | isolés sous `runtime`, jamais clés de restauration |
| `name` / titre | disponible | très volatile et potentiellement privé | indice diagnostique seulement | `title_hint`, exclu de l'équivalence structurelle |
| `scratchpad_state` | disponible sur les vues | volatile | membre/visible/caché | normalisé sous `scratchpad` |
| arbres output/root bruts | disponibles | contiennent beaucoup de runtime | diagnostic ponctuel seulement | jamais persistés dans V1 |

Une propriété absente vaut `null` lorsque l'absence est sémantique. Les
rectangles sont toujours des objets entiers `{x, y, width, height}`. V1 ne
sérialise aucune structure Python ou native opaque.

## Enveloppe et version

Chaque document porte cette identité immuable :

```json
{
  "schema": "labfy.sway.session-snapshot",
  "version": 1
}
```

La racine contient exactement les domaines contractuels suivants (des champs
compatibles pourront être ajoutés à une version mineure du producteur, mais un
lecteur doit rejeter une autre valeur de `version`) :

```text
snapshot
├── schema, version
├── metadata
├── compositor
├── outputs[]
├── workspaces[]
├── containers[]
├── windows[]
├── focus
├── restore_hints
└── diagnostics
```

### `metadata`

- `captured_at` : UTC ISO 8601 ; volatile ;
- `session_type` : valeur allowlistée, normalement `wayland` ;
- `desktop` : `XDG_CURRENT_DESKTOP`, ou repli `DESKTOP_SESSION`.

Le hostname est volontairement omis, comme le username, le chemin HOME,
l'adresse IP, la MAC et toute identité réseau.

### `compositor`

- `variant`, `version`, `sway_version` viennent de `get_version` ;
- `layout_engine` vaut `sway-native` en V1.

`layout_engine` est le point d'extension réservé à `spatial-canvas-v1` pour
STEP20. V1 n'invente ni `canvas_x`, ni `canvas_y`, ni viewport.

### `outputs[]`

Chaque output contient `name`, `active`, `focused`, `rect`, `scale`,
`transform` et `current_mode`. Le mode est `null` ou contient `width`,
`height`, `refresh_millihz`.

Le nom de connecteur est l'indice préféré, non une identité universelle.
`make/model/serial` ne sont pas des clés obligatoires. Une restauration future
devra vérifier les outputs présents, appliquer une stratégie de repli encore
à définir si un écran a disparu, puis rattacher ou redistribuer les
workspaces. V1 enregistre explicitement `missing_output_policy=deferred` : il
ne prétend pas résoudre ce cas.

### `workspaces[]`

Chaque workspace contient :

```text
name, num, output, order, focused, visible, urgent, rect,
layout, orientation, roots.tiling[], roots.floating[]
```

`num=-1` représente le comportement IPC des workspaces nommés. Un workspace
vide possède deux listes de racines vides. Chaque référence de racine vaut
`{"kind":"container|window","id":"..."}`. L'ordre des tableaux est
l'ordre Sway : il est contractuel dans le snapshot.

### `containers[]`

Un conteneur structurel contient :

```text
container_id, runtime_con_id, workspace, output,
parent_container_id, tree_position,
layout, orientation, percent, rect,
focused, urgent, marks,
children[], floating_children[]
```

`container_id` (`c1`, `c2`, …) est local au document. Les deux listes
d'enfants conservent séparément l'ordre des branches `nodes` et
`floating_nodes`. Les layouts reconnus sont `none`, `splith`, `splitv`,
`stacked`, `tabbed`, `output` et `dockarea`. Les conteneurs ne sont pas aplatis
en une liste de fenêtres : leurs relations permettent de reconstruire
l'arbre, les groupes tabbed/stacked et les proportions.

### `windows[]`

Chaque vraie vue feuille contient :

```text
window_id, snapshot_identity, runtime,
workspace, output,
app_id, xwayland.class, xwayland.instance,
executable_basename, title_hint,
restore_identity, restore_adapter, classification,
focused, urgent, floating, fullscreen_mode,
rect, percent, marks, scratchpad, tree_position
```

`window_id` et `snapshot_identity` sont locaux à cette capture. Les doublons
restent des fenêtres distinctes : par exemple `firefox#1` et `firefox#2`.
L'ordinal dépend de l'ordre déterministe de parcours de l'arbre ; ce n'est pas
une identité durable. `runtime.con_id` et `runtime.pid` décrivent seulement le
processus et le conteneur observés. Ils ne doivent jamais être utilisés après
un reboot.

`floating` combine la branche de l'arbre et l'état `auto_on/user_on`.
`rect`, `workspace` et `output` donnent les informations géométriques utiles
aux fenêtres flottantes. `fullscreen_mode` conserve la valeur entière IPC
(zéro : non fullscreen). Aucune fenêtre n'est déplacée pour compléter ces
données.

`tree_position` contient `parent_container_id`, `branch` et `index`. Une
fenêtre directement sous un workspace a un parent `null`. Une fenêtre de
scratchpad cachée n'est artificiellement rattachée à aucun workspace/output.

## Identité restaurable et DesktopEntry

Une fenêtre, un processus applicatif et une DesktopEntry sont trois niveaux
différents : plusieurs fenêtres peuvent appartenir au même processus ou à
plusieurs processus de la même application ; une DesktopEntry décrit un mode
de lancement, pas une fenêtre. Le collecteur ne fusionne jamais les fenêtres
ayant le même `app_id`.

`restore_identity` contient `app_id`, `class`, `instance`, `desktop_entry`,
`confidence` et `matched_by`. La recherche déterministe parcourt les
répertoires XDG, avec priorité aux entrées utilisateur en cas de même nom :

1. stem exact de `app_id.desktop`, `class.desktop` ou `instance.desktop` ;
2. correspondance exacte à `StartupWMClass` ;
3. stem unique égal au basename exécutable après normalisation (`heuristic`) ;
4. sinon `desktop_entry=null`, `confidence=unresolved`.

Les niveaux sont `exact`, `heuristic`, `unresolved`. Une ambiguïté ne produit
jamais de correspondance. La valeur `Exec` des fichiers desktop n'est ni
nécessaire ni persistée.

`restore_adapter` vaut actuellement `terminal`, `generic-desktop` ou
`unknown`. `kitty` ne permet pas de distinguer shell, Neovim, Yazi, SSH ou une
commande utilisateur : STEP18A n'essaie pas de le deviner. Les futurs
adaptateurs `browser` ou `custom` sont réservés à une politique ultérieure.

## Autostart et infrastructure

Le filtre primaire reste l'arbre Sway : un daemon sans fenêtre n'entre pas
dans `windows[]`. Le fichier Sway `autostart` est seulement analysé pour
classifier les programmes directs, sans exécuter leurs commandes. La
taxonomie est :

- `user-application` ;
- `autostart-managed-application` avec `managed_by=sway-autostart` ;
- `session-infrastructure` ;
- `daemon` ;
- `unknown`.

`limusic-app`, qui possède une vraie fenêtre, est classée application gérée
par `sway-autostart`. Une restauration future devra donc éviter une seconde
instance. QuickShell, l'agent Polkit, `autotiling`, le listener de
transparence, `wlsunset` et les services systemd user ne deviennent pas des
applications restaurables simplement parce que leur processus existe. La
classification ne lance rien et n'est pas encore une politique de relance.

## Scratchpad et focus

Sway expose le workspace interne `__i3_scratch`. Il est exclu de
`workspaces[]`, mais ses racines ordonnées apparaissent dans
`restore_hints.scratchpad_roots`. Chaque fenêtre porte :

- `member` ;
- `visibility` : `hidden`, `visible` ou `not-applicable` ;
- la valeur IPC `state` (`none`, `fresh`, `changed` lorsqu'elle existe).

Une fenêtre scratchpad cachée se trouve dans `__i3_scratch`; une vue membre
affichée dans un workspace réel garde un état scratchpad non `none`. L'audit
réel STEP18A a observé `__i3_scratch` vide : le cas caché est donc validé par
fixture synthétique, pas par manipulation de la session.

`focus` référence l'output et le workspace par leur nom, et la feuille ou le
conteneur par son ID local au snapshot. Ces références expriment l'état
observé ; la stratégie de restitution du focus appartient à STEP19.

## Validation et déterminisme

Le validateur interne vérifie schema/version, collections et objets
obligatoires, unicité des IDs, ordre workspace contigu, layouts admis,
relations output/workspace, références arbre, parents et cibles du focus. Le
JSON n'est émis qu'après validation. Aucune dépendance Python externe n'est
requise.

À état Sway inchangé, l'ordre de parcours IPC et du scan DesktopEntry est
déterministe. L'équivalence structurelle exclut seulement les chemins listés
dans `diagnostics.volatile_fields` :

```text
metadata.captured_at
diagnostics.collection_duration_ms
windows[].title_hint
```

Les titres restent utiles comme indices manuels mais une animation de titre,
une page Web ou un document différent ne change pas l'identité structurelle.
Les champs runtime restent inclus dans cette comparaison : à état réellement
inchangé ils doivent rester identiques.

## Sécurité et future persistance STEP18B

Un titre peut révéler un document ou un site. Les snapshots futurs sont de
l'état utilisateur et devront aller dans :

```text
${XDG_STATE_HOME:-$HOME/.local/state}/labfy-sway/sessions/
```

Le répertoire devra être créé en `0700` et chaque snapshot en `0600`. Rien ne
doit être installé dans `~/.config`, le dépôt Git, `Documents` ou `/tmp` pour
le fonctionnement normal.

STEP18B devra écrire un fichier temporaire dans le même répertoire, appliquer
les permissions, écrire et valider le document complet, effectuer `fsync` du
fichier si la politique de durabilité le requiert, puis publier par `rename`
atomique et synchroniser le répertoire si nécessaire. Une capture interrompue
ne devra jamais remplacer le dernier snapshot valide.

Sont explicitement exclus : username, HOME absolu, hostname par défaut,
IP/MAC, make/model/serial des écrans, contenu d'environnement, lignes de
commande, arguments, tokens, mots de passe, cookies, URL privées, valeur
`Exec` des DesktopEntry, arbres IPC bruts et chemins complets d'exécutables.

## Limites V1

V1 ne sait pas relancer une application, retrouver le contenu d'un terminal,
regrouper sûrement des processus en application, redistribuer un workspace si
un écran manque, restaurer le focus, interpréter un titre, faire une rotation
de snapshots ni représenter le Spatial Canvas. Ces limites sont explicites et
n'affaiblissent pas la capture normalisée de STEP18A.

Les quatre requêtes IPC ne constituent pas une transaction atomique offerte
par Sway. Si la topologie change pendant ces quelques dizaines de
millisecondes, la validation relationnelle fait échouer la capture plutôt que
de publier un graphe incohérent. STEP18B pourra effectuer une nouvelle capture
bornée ; il ne devra jamais persister le résultat invalide.
