# Validation privée prewarm et corrections P0

Campagne du 17 octobre 2026 dans
`/tmp/labfy-session-v2-final-FTMzd3h1`, baseline Git
`ec2239b436dffae0a0eb7c2fe7bada3bcabf1dc6`. Patch non commité.
Les preuves historiques SwayFX de la baseline ne constituent pas une validation
du présent patch. **Login physique NON testé**, profil Firefox réel non testé,
applications GTK synthétiques uniquement.

## Corrections et preuves déterministes

Les fixtures ont été écrites avant les changements de production. Sur le code
initial, les 17 variantes négatives initiales échouaient : absence de refus ou
première commande de mutation atteinte. Leur journal est conservé dans
`build/p0-validation/unit-before.log`. Les extensions de couverture ajoutées
ensuite ne sont pas présentées comme une campagne rouge initiale.

P0-1 : toutes les admissions gérées proviennent des observations phase0
`con_id`/PID/starttime/`app_id`/placement. Le lot est revérifié après Guard,
avant chaque staging et après résolution provider. Remplacement à cardinalité
égale et extra same-app pendant Guard : refus sans aucune commande de mutation
Executor. Un extra injecté après le premier move bloque le deuxième staging,
sans jamais cibler la nouvelle fenêtre. Les contrôles ne relancent pas Limusic.

P0-2 : `capture()` conserve l’exigence UUID exact puis précède une nouvelle
vérification de structure, membership, sortie, flottement, géométrie flottante,
focus verrouillé et identité runtime de toutes les fenêtres gérées. Nouvelle
vérification après `guard.finish()`, puis contrôle structurel fourni à
`Recovery.complete()` sur sa dernière observation. Un focus sur split transmet
sa seconde observation au contrôle structurel. PID/starttime, placement, ordre
ou pending divergents interdisent complete. Les parents unaires normalisés par
Sway sont acceptés à layout canonique, placement et ordre relatif constants.
Aucun test existant n’a été supprimé ou désactivé ; la fixture d’ancres focus
accepte désormais l’arbre optionnel, avec la même assertion canonique.

Les contrôles sont observationnels, **sans CAS Sway**. Un changement après la
dernière observation n’est pas empêché ni déclaré détecté. Le contrat ne
promet pas les ratios exacts des fenêtres tiled.

## Environnement et résultats

Le SwayFX installé répond `swayfx version 0.6 (based on sway 1.12.0)`.
L’essai headless privé GLES2 échoue avant tout scénario fonctionnel :
`drmGetDevices2 failed: No such file or directory`, puis
`Cannot create GLES2 renderer: no DRM FD available` et
`Failed to create renderer`. Journal :
`build/p0-validation/swayfx-renderer.log`.
**Validation SwayFX du patch indisponible dans ce bac à sable.**

La campagne fonctionnelle utilise le binaire déjà présent
`/tmp/limusic-test-sway-1.12/usr/bin/sway`, renderer Pixman, backend headless.
HOME et XDG sont privés, environnement construit par liste positive, aucun
SWAYSOCK/Wayland/bus réel hérité. Chaque Lab possède ses sockets et enfants.
Aucune configuration réelle, aucun autostart Sway, Mosaic ou greetd modifié.
Les helpers C sont compilés en C17 avec `-Wall -Wextra -Werror`.

Le harnais reproductible est `tests/session_v2/validate_p0.py`. Il lance deux
tests au plus simultanément et exécute QtTest séparément. Ses codes de sortie,
commandes, journaux et preuves synthétiques sont conservés dans
`build/p0-validation/release/` ; les essais antérieurs restent dans les autres
sous-répertoires, sans être écrasés.

Les essais intermédiaires ont montré un refus indu sur un chemin brut après
normalisation unaire de Sway, une fixture focus à signature ancienne, un
argument QtTest mal séparé dans le nouveau harnais et une attente de diagnostic
swap devenue trop tardive : l’ordre Recovery détecte désormais le swap avant
le layout. Ces défauts ont été corrigés, sans suppression d’assertion.

Campagne finale : **22 groupes / 22 réussis**, tous les codes de sortie à zéro.

| Suite | Résultat réel |
| --- | --- |
| `python3 -B -m unittest discover -s tests/session_v2 -p 'test_*.py'` | 41 tests OK |
| Focus Python | 28 tests OK |
| QML Python | 13 tests OK |
| QtTest QML | 5 contrôles OK, aucun skip |
| `runtime.py` | 35 scénarios OK |
| `failures.py` | 3 refus contrôlés OK |
| `crashes.py` | 10 scénarios OK |
| `security.py` | 22 contrôles OK |
| `phase3b_runtime.py` | Limusic synthétique OK, absente/dupliquée refusées |
| `phase3b_ui.py` | 7 scénarios QuickShell OK |
| `login_focus.py` | 11 scénarios OK |
| `p0_runtime.py` | 5 contre-exemples refusés comme attendu |

Le fichier `release/results.json` contient les 22 commandes et leurs codes de
sortie. Les rapports P0 incluent le rapport de tentative réel et la trace des
commandes. Le manifeste référence également les JSON des autres scénarios.
Les tests unitaires comprennent sept nouvelles méthodes, avec sous-cas
négatifs et contrôles positifs ; les 34 tests backend de la baseline passent
toujours. Les onze scénarios login sont natural, launch-failure-retry,
preserve-empty-workspace, preserve-foreign, focus-third-party,
focus-same-client, unowned-map, pinned-map, map-in-ipc-gap,
provider-placement et crash-mid-ipc.

Les cinq scénarios P0 sur compositeur réel privé sont : remplacement same-app
pendant Guard, extra same-app pendant Guard, layout pendant le troisième et
dernier capture, swap pendant ce même capture, layout pendant guard.finish.
Ils exigent tous un rapport failed, un journal non complete et un acquittement
refusé. Les deux scénarios Guard exigent zéro commande de mutation Executor.
Les tests unitaires ajoutent PID/starttime, placement, sortie, flottement,
UUID exact, focus, pending, normalisation unaire et seconde observation split.

## Reproduction sur hôte avec renderer accessible

Depuis **cette copie**, exécuter :

```sh
python3 -B tests/session_v2/validate_p0.py \
  --sway /usr/bin/sway --renderer gles2 \
  --evidence build/p0-validation/host-swayfx
```

Le harnais construit l’environnement privé ; les fixtures imposent
`WLR_BACKENDS=headless` et utilisent leurs propres sockets explicites. Il
n’utilise jamais SWAYSOCK du bureau. Il faut un accès hôte au renderer/DRM pour
SwayFX ; ne pas changer la configuration greetd ou l’autostart pour ce test.
Un refus renderer doit rester un échec de validation, pas un PASS.

Pour reproduire la campagne Pixman du bac à sable avec le binaire présent :

```sh
python3 -B tests/session_v2/validate_p0.py \
  --sway /tmp/limusic-test-sway-1.12/usr/bin/sway --renderer pixman \
  --evidence build/p0-validation/reproduction-pixman
```

Les SHA-256 du patch, des fichiers livrés et des journaux sont dans
`build/p0-validation/manifest.json`. Le patch complet est
`build/p0-validation/session-v2-p0.patch`. Ces artefacts ne contiennent pas
les travaux build préexistants et ne nécessitent aucun staging Git.
