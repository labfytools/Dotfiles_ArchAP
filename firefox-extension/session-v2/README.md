# Companion Firefox Session Restore V2

Sources de la version **1.1.2**, même ID `session-v2@labfy.org`, même clé
`labfy.session.window_uuid`, mêmes permissions `sessions`, `nativeMessaging`.
Le build local produit un XPI non signé. Son installation permanente nécessite
une signature Mozilla, en conservant cet ID et les identités de fenêtres existantes.
Aucun accès aux profils, au runtime utilisateur ou au socket Sway réel n'est
nécessaire pour les validations décrites ici. Elles ne réalisent aucun déploiement permanent.

L'expérience visée est **installation seule, puis Firefox normal, Ctrl+N compris**.
Le bouton et le panneau provisoires de 1.1.0 sont supprimés. Le background ne
crée aucune fenêtre. Une fenêtre ambiguë peut rester sans identité et faire
échouer la capture ; aucune action quotidienne de remplacement n'est imposée.

## Correctif 1.1.2 : séparer les webapps du lot UUID

Une fenêtre Firefox Taskbar Tab peut être exposée par l'API WebExtension comme
`type: normal`, alors que SessionStore l'exclut du stockage de session. Un UUID
attribué dans sa fenêtre pendant une session peut donc manquer au login suivant.
La 1.1.1 validait l'ensemble des fenêtres normales avant toute publication : une
webapp sans UUID bloquait aussi la capture du navigateur ordinaire. Si toutes
les valeurs étaient présentes, l'ordre des fenêtres pouvait masquer ce défaut :
le host ne corrélait que `firefox`/`org.mozilla.firefox`, et un navigateur publié
avant la webapp pouvait suffire au backend avant l'échec ultérieur du lot.

Sources Firefox vérifiées, y compris dans les `omni.ja` installés :
`TaskbarTabsWindowManager.sys.mjs` ouvre avec toolbar et sans dialog ;
[WindowBase.type](https://searchfox.org/firefox-main/source/toolkit/components/extensions/parent/ext-tabs-base.js)
classe alors la fenêtre comme normale ;
[windows.getAll](https://searchfox.org/firefox-main/source/browser/components/extensions/parent/ext-windows.js)
filtre ce type seulement. Dans SessionStore, `getCurrentState()` et la collecte
des fenêtres fermées excluent explicitement `isTaskbarTab`. L'API Window ne
fournit aucun attribut public `isTaskbarTab` ou `app_id` permettant ce filtrage.

La 1.1.2 ajoute une classification native avant toute lecture ou attribution
UUID. Elle conserve les permissions `sessions` et `nativeMessaging`, l'ID de
l'extension et la clé de session existants. La demande est exactement :

```json
{"op":"classify-window","runtime_token":"0123456789abcdef0123456789abcdef"}
```

Le host corrèle le préfixe éphémère, puis vérifie les app_ids exacts des entrées
Firefox et WhatsApp gérée du catalogue. Sa réponse fermée comporte `result`,
`kind`, `runtime_token` réémis et `con_id` positif. `kind` vaut exclusivement
`browser` ou `managed-webapp`. Un app_id inconnu, une autre webapp, une collision,
un timeout ou une réponse invalide refuse l'opération ; aucune erreur n'est
interprétée comme une permission d'ignorer une fenêtre. La classification ne
publie aucun enregistrement UUID. `map-window` reste réservé à Firefox ordinaire.

Le background exclut seulement une webapp positivement attestée avant
`getWindowValue`, validation, observation ou mint. Une fenêtre normale sans UUID
continue à refuser la capture exacte. Les règles de protection des anciennes
fenêtres et d'attribution aux nouveaux Ctrl+N restent identiques.

Les preuves `{kind, con_id}` sont bornées à 256 fenêtres, locales à l'instance et
supprimées sur fermeture. La première observation classe une fenêtre une fois ;
une erreur n'est pas retentée par la boucle idle. Chaque capture reclassifie
fraîchement toutes les fenêtres, y compris celles qui seront exclues, puis
revalide après l'attente d'extData. Chaque mint revalide aussi la classe avant
écriture. Un changement de classe ou de con_id interdit l'opération jusqu'à la
fermeture de cette fenêtre. L'ensemble brut des fenêtres doit rester stable
pendant l'opération. Aucun marquage ou `map-window` périodique permanent n'est
ajouté en veille.

La corrélation ajoute des préfixes brefs lors du premier classement, d'une capture
ou d'un mint ; elle utilise les mêmes garanties de nettoyage et limites API que
le protocole existant. Elle ne rend pas le sessionstore transactionnel. Un host
ancien ne comprenant pas la classification provoque un refus conservateur ; le
nouveau host reste compatible avec les messages de l'extension 1.1.1.

Les tests VM de cette révision couvrent la webapp au premier ID sans UUID, son
exclusion des lectures et écritures, la normale sans UUID toujours refusée, les
réponses non exactes, le changement de classe/con_id, l'invalidation sur close,
le changement d'ensemble et l'absence de marquage répété en idle. Le code testé
est celui du XPI. La validation Python du host reste séparée de tout profil ou
socket utilisateur. La régression a également été reproduite puis corrigée sous
Firefox réel 158.0.1 dans un profil vierge et un Sway privé (détails plus bas).

La mise à jour nécessite un nouveau XPI signé Mozilla, avec le même ID. Déployer
le host compatible avant l'installation de l'extension signée ; son redémarrage
déconnectera l'ancien port natif et ouvrira le nouveau host. Ne pas modifier le
contenu d'un XPI signé, désactiver les signatures ou réattribuer les anciens UUID.
Le build ci-dessous prépare seulement le XPI déterministe non signé : aucune
signature, publication AMO ou installation n'est réalisée par le build.

## Preuves disponibles et limite fondamentale

La 1.0.0 pouvait attribuer après `undefined` et seulement 200 ms, donc écraser
une identité arrivée plus tard. L'incident historique (onglets conservés, UUID
modifié entre deux logins) est compatible avec cette course, sans en prouver la
cause précise. L'extension ne répare ni cet UUID perdu ni les checkpoints.

Sources primaires consultées pour cette révision :

- [getWindowValue](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/sessions/getWindowValue)
  conserve les valeurs lors de close/restore, avec un autre windowId runtime.
  Son exemple inclut les fenêtres restaurées dans `onCreated`. `undefined` et
  rejet sont deux résultats distincts ; aucun délai maximal d'extData n'est fourni.
- [onChanged](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/sessions/onChanged)
  signale des changements de liste fermée, sans provenance de fenêtre.
- [Window.sessionId](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/windows/Window)
  identifie une fenêtre obtenue via l'API sessions. Sa présence est utilisée
  uniquement pour protéger ; son absence ne prouve jamais une création neuve.
- [sessions.restore](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/sessions/restore)
  renvoie la session restaurée lorsque l'extension appelle elle-même cette API.
  Cela n'identifie pas directement une restauration effectuée par l'utilisateur.
  `getRecentlyClosed` fournit une liste bornée, pas une correspondance certaine
  entre ses éléments et chaque événement `windows.onCreated`. Nous ne l'utilisons
  pas comme preuve, et n'inspectons aucun contenu d'onglet.
- [Événements SessionStore Gecko](https://firefox-source-docs.mozilla.org/browser/components/sessionstore/docs/events.html)
  documente `sessionstore-windows-restored` comme notification interne de fin du
  startup. Ce n'est pas un événement de WebExtension standard. Les
  [API privilégiées/Experiments](https://firefox-source-docs.mozilla.org/toolkit/components/extensions/webextensions/basics.html)
  ne constituent pas une voie AMO ordinaire pour ce candidat Firefox Release.
- [runtime.onInstalled](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/runtime/onInstalled)
  distingue explicitement `install`, `update`, `browser_update`.

**Conclusion de conception :** les observations répétées et une période calme
réduisent le risque ; elles ne prouvent pas la fin de toutes les restaurations.
Une restauration manuelle/tardive sans signal exploitable, dont l'ancienne valeur
reste absente jusqu'après la dernière lecture, est indiscernable d'un Ctrl+N.
Elle peut recevoir un nouvel UUID dans ce compromis automatique. Une valeur
ancienne arrivant entre la dernière lecture et l'écriture peut encore être
écrasée : `setWindowValue` n'offre pas de compare-and-set. Les contrôles après
écriture ne suppriment pas ce risque. **Aucune garantie absolue de classification
ou d'absence d'écrasement de données jamais encore observées n'est revendiquée.**
Garantir cela pour toutes les restaurations exigerait une preuve supplémentaire
fournie par Firefox ; refuser tout mint sur `onCreated` supprimerait l'auto Ctrl+N.
L'automatisme de 1.1.1 est conservé avec refus des ambiguïtés observables.

## Initialisation : BOOT, READY, PROTECTED

Les listeners sont enregistrés avant tout appel asynchrone. Le premier `getAll`,
sans populate, capture les IDs de la baseline. Une fenêtre émise **avant la
résolution** de cette photographie reste ambiguë, même si `getAll` la contient.
Un événement reçu ensuite, y compris pendant BOOT, devient candidat potentiel :
`type` normal ou absent, sans `sessionId` positif. Sa présence dans
`getAll({windowTypes:["normal"]})` et une classification native fraîche `browser`
seront exigées avant toute écriture. Les types explicitement différents de normal
sont ignorés ; une webapp de type normal est exclue seulement après attestation.

**Auto-baseline sans clic, sous attestation native.** L'événement
`onInstalled(reason=install)` est mémorisé qu'il précède ou suive le premier
`getAll`. Il autorise seulement une tentative de lot après stabilisation.
`update`, `browser_update` et restart ne l'autorisent jamais. Avant **chaque**
écriture de baseline, l'extension envoie exactement :

```json
{"op":"bootstrap-eligibility"}
```

Le host répond avec exactement deux champs, sans chemin ni contenu utilisateur :

```json
{"result":"OK","baseline_enrollment_allowed":true}
```

`true` signifie que le checkpoint automatique V2 canonique
`automatic/last.json` est absent **et** que `sessions` est absent ou vide
(aucune sauvegarde nommée ni entrée inattendue), à l'instant du contrôle, sous l'autorité
`XDG_STATE_HOME` ou son fallback HOME habituel. Le chemin est commun au store et
au host ; l'extension ne le reçoit pas. Le parcours utilise des descripteurs de
répertoires et `NOFOLLOW`, sans créer le store, ouvrir le checkpoint ou suivre un
lien. Toute présence, même fichier corrompu, illisible, lien ou FIFO, refuse.
Le host examine les deux branches même si l'une est absente. `sessions` est
énuméré par `os.listdir(dirfd)` sans ouvrir ses entrées ; tout fichier, lien,
FIFO ou sous-répertoire refuse. Le chemin est limité à 4096 octets ; un
répertoire `sessions` dont la taille de métadonnées dépasse 64 Kio refuse
avant énumération. Ce budget conservateur ne certifie aucune absence.
Une erreur, un parent inaccessible, un namespace non privé ou un chemin invalide
refuse aussi. Le host revalide le socket et l'UID du pair Sway par `GET_VERSION`,
en lecture seule, sans demander l'arbre des fenêtres pour cette opération.

Seules les fenêtres de la photographie initiale encore sans valeur, sans
identité déjà observée ni tentative d'écriture et sans signal protecteur sont
éligibles. Deux fenêtres initiales sans UUID reçoivent ainsi automatiquement
deux UUID distincts si le host atteste l'absence à chaque contrôle et si les
relectures Firefox restent stables. Les fenêtres signalées avant la photographie
ou avec `sessionId` positif restent protégées. Après réponse positive : relecture
intégrale du lot, révision inchangée et dernière absence exigées avant écriture.

**Une installation seule ne garantit donc pas l'enrôlement.** Host indisponible,
réponse non exacte, refus, déconnexion ou timeout de 5 secondes : aucune
attribution de baseline concernée ; elle reste en quarantaine. Une activité
pendant le lot révoque la tentative. Aucun retry d'autorisation baseline dans
cette instance, même après reconnexion ou nouvel événement install. Si le
checkpoint apparaît entre deux écritures, la seconde est refusée ; aucune
annulation de l'UUID déjà écrit. Les futurs Ctrl+N, y compris ceux reçus pendant
BOOT après photographie, conservent leur automatisme indépendamment du refus.

Cette attestation concerne les checkpoints V2 automatiques et nommés à leurs
emplacements canoniques. Elle ne prouve ni l'absence historique de sauvegardes,
ni l'absence de sauvegardes déplacées, ni la provenance des restaurations tardives
Firefox. Elle n'est ni un verrou
persistant, ni un CAS ACID, ni un observer sessionstore ; un checkpoint peut
apparaître après la dernière réponse. Aucun checkpoint ou navigateur n'est
modifié par cette observation native.

BOOT attend au moins 30 secondes depuis le chargement, 2 secondes sans activité
et l'expiration du guard de 5 secondes suivant `sessions.onChanged`. Ensuite la
phase passe READY même si des anciennes fenêtres restent ambiguës. Celles-ci
bloquent **la capture exacte**, mais ne condamnent plus les futurs Ctrl+N, y
compris après 60 secondes et après fermeture de l'ancienne fenêtre. PROTECTED
reste un refus opérationnel, notamment si la photographie initiale échoue ; un
timeout API exige un redémarrage. Ces délais sont des budgets, pas une barrière
sessionstore ni une preuve de nouveauté.

Un Ctrl+N à 10 secondes, après photographie initiale, reste en attente puis reçoit
automatiquement son UUID après stabilisation et observation. Une restauration
sans signal dans ce même intervalle est indiscernable : le timing ne la rend pas
« prouvée nouvelle ». Une identité reçue pendant l'attente est préservée.

## Fonctionnement automatique après READY

Un passage périodique unique par seconde observe le lot complet. Chaque absence
candidate doit persister durant 2 secondes de lectures espacées de 250 ms. Dans
le cas normal, l'UUID apparaît environ 2 à 3 secondes après Ctrl+N, sans action sur
l'extension. Les anciennes fenêtres ambiguës restent exclues, sauf la baseline initiale
explicitement admissible sous l'attestation décrite ci-dessus.

Avant chaque écriture : relecture intégrale, ensemble inchangé, identités connues
inchangées, UUID v4 valide, absence de collisions visibles, révision inchangée.
Deux Ctrl+N simultanés ou espacés d'une seconde reçoivent des identités distinctes
après réobservation du lot stable. L'ordre numérique des IDs sert seulement à
sérialiser les opérations. Aucune unicité sur toutes les fenêtres fermées de
l'histoire n'est prouvée ; la génération repose sur `crypto.randomUUID`.

`sessions.onChanged` peut signaler une simple fermeture d'onglet. Il invalide le
passage en lecture et diffère les candidats pendant le guard, sans les mettre
en quarantaine définitive. Une modification de révision ou d'ensemble avant
écriture abandonne le passage ; les mêmes candidats sont réobservés après calme.
Les rejets de lecture, identités invalides ou divergentes et écritures incertaines
restent des refus conservateurs. La présence de `sessionId` ou un événement avant
la photographie initiale protège individuellement la fenêtre concernée.

Une valeur observée, même dans un lot partiellement rejeté ou invalide, ne peut
jamais devenir une autorisation de mint. Changement,
disparition ou collision refuse le lot. Aucune suppression de valeur et aucun
rollback d'identité. Une seule tentative d'écriture par fenêtre/instance ; un
rejet peut cacher un effet appliqué et n'est jamais réessayé. Vérification par
relecture avant de libérer l'opération. Un restart perd toute autorité de mint en
attente et ne conserve comme vérité que les valeurs de session.

Ni onglets, ni URL, ni titres, ni géométrie, ni ordre, ni PID n'identifient une
fenêtre. Aucune lecture/écriture de tab data ; déplacer des onglets n'entraîne
aucun transfert d'identité ni fusion de fenêtres.

## Capture native et bornes

La capture native reste **non-mutante pour l'identité et les onglets**. Elle relit
un lot incomplet pendant 2 secondes puis refuse sans publication. Elle peut
récupérer une valeur arrivée plus tard lors d'une nouvelle capture. Lot complet
revalidé avant publication et UUID relu avant chaque message. Aucun protocole
atomique avec Firefox ou transaction native de lot n'est prétendu.
Le préfixe `titlePreface` éphémère de corrélation, déjà présent dans 1.1.0, reste
la seule mutation de présentation ; nettoyage en `finally` et au démarrage.
Si l'appel de marquage expire puis se règle tardivement, un seul effacement de
secours est lancé après son règlement, sans relancer le marquage. Si l'appel ne
se règle jamais, ou si l'effacement bloque/rejette, le préfixe peut rester visible
jusqu'au redémarrage/nettoyage réussi. Aucune API WebExtension ne permet d'assurer
une borne de disparition face à une API définitivement bloquée ; le préfixe ne
peut donc pas être qualifié d'inconditionnellement éphémère.
Les titres eux-mêmes ne sont jamais lus.

Une seule opération active (initialisation/nettoyage, auto-mint ou capture) ;
captures concurrentes coalescées sans queue, sans accumuler des opérations.
Une demande native en vol ; timeout 5 secondes ; reconnexion au plus une fois par
seconde, sans map-window en idle. Les classifications de première observation
sont mises en cache, sans répétition périodique. Le backend existant garde son timeout de 6 secondes :
un checkpoint trop tôt ou durant un mint peut échouer, il ne reçoit pas de faux
succès ni d'identité inventée par la capture.

Chaque appel Firefox a une borne de 2 secondes. Un timeout arrête les appels
Firefox ordinaires de cette instance jusqu'au redémarrage (seul l'effacement
de secours après règlement du marquage peut encore être tenté) ; les promesses ne sont pas
annulables et un effet tardif reste possible. Les lectures sœurs sont toutes
attendues même si l'une rejette. Limite locale conservée : 256 fenêtres.
Les ensembles en mémoire sont bornés aux fenêtres suivies et nettoyés sur close.
Le provider Python exact, le format et le contenu des checkpoints et les
applications SwayFX restent inchangés. Le host ajoute les opérations
d'observation bootstrap et de classification au protocole de mapping existant. Une capture refusée ne publie pas un message d'erreur incompatible :
le provider existant échoue faute du lot demandé. Le diagnostic facultatif
`runtime.sendMessage({op: "identity-status"})`, réservé à cette extension, retourne
phase, résultat WAIT/READY/REFUSED, dernier motif et compteurs ; il n'attribue rien.
Le résultat READY exige la phase READY, aucune erreur, aucune quarantaine et
aucun candidat en attente. La phase READY seule peut coexister avec un résultat
REFUSED pour ambiguïté historique. `prefixCleanupPending` expose un effacement
de secours non confirmé. Aucun panneau ni clic quotidien n'est ajouté.

## Validation et build local

Depuis la racine de cette copie :

```sh
node --test tests/firefox_session_v2/*.test.js
node --check firefox-extension/session-v2/background.js
python3 -B -m unittest discover -s tests/session_v2 -p 'test_*.py'
python3 -B tools/build-session-v2.py --extension-only
sha256sum build/session-v2/labfy-session-v2-unsigned.xpi
```

Le XPI déterministe ne contient que `manifest.json` et `background.js`.
`extension-manifest.json` indique SHA-256, `signed: false`, `installed: false`.
Deux builds locaux sont comparés octet pour octet. Le build complet historique
sans `--extension-only` reste disponible ; aucun helper n'est installé ici.

Lint ESLint 9.39.1 épinglé, outil isolé dans la copie (pas le validateur AMO) :

```sh
mkdir -p build/session-v2
touch build/session-v2/npm-user.conf build/session-v2/npm-global.conf
npm --userconfig "$PWD/build/session-v2/npm-user.conf" \
  --globalconfig "$PWD/build/session-v2/npm-global.conf" \
  exec --cache ./build/session-v2-npm-cache --yes --package eslint@9.39.1 -- \
  eslint --no-config-lookup --no-ignore \
  --rule 'no-unused-vars:error' --rule 'no-undef:error' \
  --global browser --global crypto --global performance \
  --global setTimeout --global clearTimeout --global setInterval \
  firefox-extension/session-v2/background.js
```

Les tests Node exécutent le vrai background dans une VM : APIs WebExtension,
ports natifs et temps synthétiques. Des getters interdits détectent toute lecture
d'URL, titre, onglets, dimensions ou API tabs, même si le background attrape
l'exception. Ils couvrent installation avant/après start, Ctrl+N, boot ambigu,
extData tardives, restauration signalée, absence de signal (limite exposée),
erreurs et timeout, collisions, close, déplacements d'onglets, restart/update,
concurrence et reconnexion. Les 46 tests Node présents dans la copie initiale sont conservés avec leur
comportement protecteur lorsque le host n'atteste pas l'absence. Le nouveau P0
échoue contre le background pré-protocole conservé en preuve, puis passe contre
le correctif. La validation historique 1.1.1 comptait **58 tests Node** et **63 tests Python**
(les 43 backend préexistants et 20 tests bootstrap). La révision 1.1.2 conserve ces
58 scénarios Node et ajoute 10 régressions de classification : **68/68 PASS**.
Les tests ciblés du host passent **30/30** : les 20 tests bootstrap existants et
10 tests de classification. Ils vérifient l'enveloppe fermée, le jeton exact, les
classes du catalogue, les collisions même avec une surface inconnue, la réponse
sans contenu, l'absence de publication UUID et le refus de mapper une webapp.
Ces tests Python passent par le framing stdio réel du host avec HOME/XDG privés
et un faux socket Sway
possédé, y compris aller-retour bootstrap/map/bootstrap, checkpoint présent,
valide, corrompu ou inaccessible, sauvegarde nommée seule sans `last.json`,
répertoires vides, entrées inattendues dans `sessions`, liens, FIFO, permissions,
erreur d'énumération, enveloppes invalides et allowlist.
Les scénarios VM ajoutés couvrent les deux ordres install/start, le refus,
l'expiration, les réponses non exactes, la capture concurrente, le rollback,
la relecture avant écriture, le checkpoint apparu entre écritures et les
reconnexions sans retry baseline. Le risque de restauration indiscernable est
exposé par un test ; il ne constitue pas une preuve de classification parfaite.

Les validations VM historiques 1.1.1 ne lançaient pas Firefox réel et ne
prouvaient pas le comportement physique de SessionStore. Le test réel 1.1.2
ci-dessous ajoute une preuve de capture ; il ne constitue pas un logout/login
de la session utilisateur. Le minimum de manifeste reste Firefox 157. Le
déploiement permanent de 1.1.2 avec le même ID nécessite une signature Mozilla
et une installation autorisée ; les tests et le build ne signent ni ne publient.

### Régression Firefox réelle 1.1.2

Le 27 octobre 2026, le scénario a été exécuté sous Firefox **158.0.1** avec un
profil vierge, HOME/XDG privés, serveur HTTP loopback et Sway headless privés.
Marionette et l'installation temporaire de l'extension sont confinés à ce
profil TEST_ONLY ; aucun profil, cookie, checkpoint ou fenêtre utilisateur
n'est utilisé. La webapp est créée avant la fenêtre normale, sans UUID ;
la normale reçoit une identité fixture stable avant l'installation temporaire.

Avec la 1.1.1, la capture reproduit
`FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE`. Avec le XPI 1.1.2 et le host de cette
révision, elle réussit : correspondance exacte UUID/con_id de la normale,
UUID normal inchangé et aucun UUID attribué à la webapp. Cela confirme aussi
que le préfixe éphémère d'une vraie Taskbar Tab atteint Sway et permet sa
classification native. Résultat final : **PASS**.

Reproduction du candidat construit dans cette copie :

```sh
python3 -B tests/session_v2/firefox_webapp_runtime.py \
  --extension build/session-v2/labfy-session-v2-unsigned.xpi --expect success
```

Le script émet un résultat JSON avec seulement les verdicts et la version,
dans son répertoire temporaire TEST_ONLY. Il ferme ses processus et ressources
privés. Cette validation ne prouve pas la persistance au prochain login réel,
la signature AMO ni le déploiement permanent de l'extension.

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

Le host accepte `map-window` avec UUID et jeton runtime, `classify-window`
avec son seul jeton runtime, ainsi que `bootstrap-eligibility` sans autre champ.
Les trois schémas sont fermés. La classification atteste seulement le type local ;
elle ne crée, ne modifie ni ne publie d'UUID.
Les messages sont bornés à 4096 octets ; la sortie standard est réservée au
framing Native Messaging. Le host lit l’arbre Sway uniquement pour corréler le préfixe
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

## Verdict historique du correctif 1.1.1

**SOURCE_TESTED — AUTO_BOOTSTRAP_CONDITIONNEL** : dans la VM, première
installation avec deux fenêtres sans UUID et absence attestée de checkpoint :
deux identités stables attribuées automatiquement. Réinstallation avec checkpoint
présent, contrôle inaccessible ou erreur : refus conservateur. Les Ctrl+N restent
automatiques. Les preuves, empreintes, logs et patch non commité sont conservés
dans `build/bootstrap-evidence/` de cette copie privée.

**État de la validation historique 1.1.1 : Firefox Release n'avait pas été
lancé par cette validation VM.** Aucun PASS de login réel, de persistance
physique ou de déploiement n'était revendiqué. L'artefact 1.1.1 alors construit
était non signé ; il nécessitait une signature AMO et une installation
ultérieures. Le test Firefox réel ajouté pour 1.1.2 est décrit ci-dessus. La provenance d'une restauration tardive sans signal reste
inconnue ; une ancienne valeur jamais encore visible peut toujours arriver entre
la dernière lecture et l'écriture. Aucune garantie absolue de CAS ou de protection
d'une identité jamais observée n'est annoncée. Aucune réparation d'UUID perdu,
réécriture de checkpoint ou modification du PC réel n'a été effectuée.
