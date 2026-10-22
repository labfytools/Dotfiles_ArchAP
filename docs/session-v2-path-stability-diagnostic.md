# Premier login V2 : chemins de feuilles après Guard

Suite du diagnostic : [focus et récupération du 22 octobre](session-v2-focus-recovery-fix-v1.md).
Cette page conserve la portée et les résultats de la correction précédente.

## Résultat et portée

Correction minimale dans la seule copie
`/tmp/labfy-session-v2-path-stability-LrpgZuut`, basée sur
`8a4d829ce78b67fe1d4ff910c89d3278d81b6e85`, sans commit ni déploiement.
La contradiction entre comparaison post-Guard et admission est corrigée.
**Le login graphique physique reste non validé.** Les résultats ci-dessous
concernent des applications GTK synthétiques, deux UUID Firefox synthétiques
stables et des compositeurs enfants TEST_ONLY. Ils ne valident pas les profils
Firefox réels, leurs codecs ni le premier login SwayFX sur le bureau.

Le dernier login réel a échoué **après l’intégration des protections P0**.
Les validations antérieures ne doivent pas masquer cet échec. Les journaux
réels sont préservés : ils n’ont été ni recherchés, ni lus, ni modifiés pendant
cette mission. Les faits réels suivants sont uniquement ceux fournis au ticket.

## Faits reçus et hypothèse

Vers 16:51, refus `TARGET_OBSERVATION_CHANGED`, phase `cleanup-error`,
`operations=0`, `anchors_created=0`, un helper suspendu puis repris.
Recovery avait admis Kitty7 et Firefox8 ; aucun déplacement ni swap n’a eu lieu.
L’échec à l’admission de Firefox10 est vraisemblable, pas établi par une trace
complète de chaque admission.

Le checkpoint comporte quatre slots : en 1,
`splitv(Firefox1, splith(Firefox2, Kitty))`, et Limusic en 10. Les deux Firefox
ont des UUID exacts distincts. La nouvelle session contient Firefox8 et
Firefox10 de même PID, Kitty7 et Limusic5. Des parents internes unaires peuvent
faire passer les chemins, par exemple, de `[0]` à `[0,0]` ou de `[1,0]` à
`[1,0,0]`, sans changer les feuilles, leur ordre ou leur placement.

**Hypothèse forte, non preuve historique :** Sway/autotiling a ainsi décalé les
chemins entre phase 0 et admission. Les chemins exacts de la preuve PREWARM ne
sont pas archivés. La reproduction contrôlée prouve le défaut du code et sa
correction dans ce cas ; elle ne reconstruit pas rétroactivement le login.

## Contradiction et correction

`Executor._check_prepared(before, after)` autorise déjà les variations de
chemin si le lot exact, con_id/PID/starttime/app_id, workspace/output,
flottement, géométrie pertinente et ordre relatif des feuilles restent stables.
Après Guard, `_apply` faisait cette comparaison puis passait à
`Recovery.admit(node, prepared[id])` l’ancien chemin de phase 0.
`admit` exige une égalité complète, chemin inclus : il refusait donc une
variation que le contrôle précédent venait d’accepter.

Le patch conserve l’observation courante post-Guard, la compare au lot de
phase 0, puis l’utilise comme lot canonique pour toutes les admissions initiales.
Chaque admission relit encore strictement son observation épinglée. Le lot
entier est admis avant le premier déplacement. Un changement après cette
capture n’est pas accepté par simple réobservation. Aucun changement à Recovery,
au journal, à la preuve de focus, aux codecs Firefox ou au catalogue n’est requis.

La preuve initiale de focus de phase 0 reste contrôlée strictement à la
création de Recovery. La variante « après phase 0 » injecte après cette
validation, dans la construction d’Anchors avant Guard ; elle ne renouvelle
pas artificiellement la preuve initiale. La variante « pendant Guard » injecte
uniquement après la construction réelle de Guard et avant son retour à
Executor. Les injections vérifient l’identité du focus actif, sans prétendre
que la topologie complète de `focus_proof` est inchangée ni en attribuer la cause.
Un changement avant la validation initiale de cette preuve peut donc toujours
être refusé par `RESTORE_FOCUS_UNSTABLE`.

Après les déplacements possédés, `Recovery.command` actualise les états
`expected`, chemins compris, de toutes les fenêtres admises. Les pins
post-provider sont pris après ces commandes : les nouveaux chemins possédés
sont correctement acceptés. Le provider n’est pas une mutation possédée de
placement : une insertion unaire pendant son attente reste refusée par
l’égalité stricte de `admit`. Aucune relaxation supplémentaire n’a été ajoutée.

## Régressions et résultats

Le test graphique a été écrit et exécuté avant la correction. Sur la baseline,
l’injection pendant Guard produit `TARGET_OBSERVATION_CHANGED`, zéro commande,
zéro ancre et zéro swap. La reproduction des quatre variantes positives a
ensuite été rejouée contre l’Executor de HEAD dans un backend temporaire,
avec le même test final : les quatre refusent avant correction, sans commande.
Ces échecs attendus sont conservés sous `build/path-stability/avant-final/`
et dans `avant-final.log` ; le premier échec est aussi sous `avant/`.

Après correction, les variantes suivantes réussissent sur Sway 1.12/Pixman :

- Parents unaires horizontaux/verticaux autour des trois fenêtres en 1,
  uniquement pendant Guard, avec focus actif inchangé.
- Insertion après la preuve de phase 0, avant Guard.
- Insertions réparties entre ces deux frontières.
- Même scénario avec un vrai autotiling enfant, suspendu puis repris une fois.

Chaque succès exige quatre swaps, quatre slots, statut `success`, journal
`complete`, deux vérifications finales vraies, arbre exact en 1 et 10 et
un seul Limusic. Les deux Firefox sont des surfaces du même processus et leurs
UUID exacts sont résolus par un provider synthétique stable.
L’autotiling testé est un enfant privé ; seuls son PID et son socket sont
fournis à la découverte du test. Les splits déterministes sont injectés par le
contrôleur de test. Ce scénario ne prouve pas qu’autotiling a causé le refus réel.

Les deux nouvelles méthodes backend comportent 17 sous-cas de refus à la
frontière Guard ou après la capture canonique : ordre, PID, starttime,
remplacement Firefox8 ou Firefox10 par 21 (mêmes app_id/PID et cardinalité), Firefox
supplémentaire, workspace, output, flottement, focus tiers, Limusic dupliqué,
chemin/identité/membres/focus modifiés après capture et entrée pending.
Elles exigent zéro commande et aucun build d’ancres. Une cinquième expérience
graphique modifie les chemins pendant le provider et exige le refus
`TARGET_OBSERVATION_CHANGED`, zéro swap et aucune commande après cette attente.
Les anciens tests de crash mid-IPC, intentions durables et dernière capture
provider restent inchangés et passent.

Campagne `build/path-stability/campagne/results.json` : **23 groupes réussis**.

| Suite | Résultat |
| --- | --- |
| Backend, anciens P0 et nouvelles frontières | 43 tests OK |
| Focus Python | 28 tests OK |
| QML Python | 13 tests OK |
| QtTest | 5 contrôles OK, aucun ignoré |
| Runtime | 35 scénarios OK |
| Erreurs contrôlées | 3 scénarios OK |
| Crash/SIGKILL | 10 scénarios OK |
| Sécurité | 22 contrôles OK |
| Runtime Limusic | Succès, absence et duplication contrôlés |
| UI QuickShell headless | 7 scénarios OK |
| Anciens login Focus | 11 scénarios OK |
| P0 headless | 5 contre-exemples refusés comme attendu |
| Chemins post-Guard/provider | 4 succès exacts et 1 refus attendu |

Les helpers C sont compilés en C17 avec `-Wall -Wextra -Werror` par les fixtures.
Les contrôles UTF-8 des pages Session V2 et `git diff --check` sont consignés
séparément dans `controles-finaux.log`.

L’essai privé sur le SwayFX installé (`/usr/bin/sway`, GLES2) échoue avant
création du serveur : `drmGetDevices2 failed`, `no DRM FD available`,
`Failed to create renderer`. Le log est `swayfx/resultat.log`.
C’est une **validation fonctionnelle indisponible dans le sandbox**, pas un
PASS SwayFX. Le binaire Sway 1.12/Pixman préexistant sous `/tmp` a permis la
campagne fonctionnelle sans installation ni remplacement système.

## Reproduction sur ArchASP

Depuis cette copie, avec le renderer de l’hôte accessible :

```sh
python3 -B tests/session_v2/validate_p0.py \
  --sway /usr/bin/sway --renderer gles2 \
  --evidence build/path-stability/hote-swayfx
```

Cette commande inclut les nouveaux tests de chemins et toutes les suites
précédentes. Le harnais définit un environnement positif HOME/XDG privé ; chaque
Lab démarre son compositeur headless enfant, son Wayland et son socket Sway
explicite TEST_ONLY. Il n’utilise pas le socket du bureau. Aucun reload,
logout, redémarrage, changement d’autostart ou de greetd/mosaic n’est requis.
Un refus de renderer garde un code non nul et doit être signalé séparément.

La campagne équivalente réalisable dans ce sandbox est :

```sh
python3 -B tests/session_v2/validate_p0.py \
  --sway /tmp/limusic-test-sway-1.12/usr/bin/sway --renderer pixman \
  --evidence build/path-stability/reproduction-pixman
```

## Livraison et conditions restantes

`build/path-stability/session-v2-path-stability.patch` contient le patch exact,
y compris les nouveaux tests et cette documentation, sans staging ni commit.
`manifest.json` contient le SHA de base Git, les SHA-256 des fichiers livrés,
du patch et des preuves, les commandes et les résultats. Les artefacts de
construction ne font pas partie du patch. Aucun journal utilisateur réel
n’est inclus.

La correction est bornée à l’incohérence de snapshot démontrée. Une différence
d’identité, membres, placement, ordre, focus externe ou une intention ambiguë
reste bloquante. Le contrôle GET_TREE puis IPC n’est pas atomique : une mutation
postérieure à la dernière observation ne peut être exclue par cette interface.
Les chemins inconnus à la prochaine vérification sont refusés ; un crash après
intention durable conserve le besoin de recovery. Ne pas transformer ces
refus conservateurs en succès par app_id ou cardinalité.

Restent à valider séparément : cette nouvelle version sur le renderer SwayFX
hôte, puis un véritable login graphique physique et les applications réelles.
Aucune action sur la session réelle n’a été effectuée ou autorisée ici.
