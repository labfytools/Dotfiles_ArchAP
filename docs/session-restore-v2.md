# Session Restore V2

La recette réelle du 7 octobre 2026 a réussi : logout, checkpoint V2, arrêt par
UWSM, login, chooser unique et un clic **Restaurer**. Aucune interaction après
ce clic ; arbre, focus final et identité Firefox exacte vérifiés. La validation
visuelle utilisateur est PASS. Les preuves détaillées restent dans la branche
locale de recherche ; elles ne sont pas distribuées dans ce dépôt.

## Utilisation

Le menu power conserve Verrouiller, Suspendre, Déconnexion, Redémarrer et
Éteindre. Déconnexion sauvegarde un checkpoint V2 avant `uwsm stop` ; Redémarrer
et Éteindre sauvegardent avant leur action systemd. Un échec de checkpoint
permet d’annuler ou de choisir explicitement de quitter sans sauvegarder.

Au login suivant, le chooser propose Restaurer ou Nouvelle session. Un clic
Restaurer lance la transaction jusqu’au résultat final, sans étape Firefox
manuelle ni deuxième restauration. Le chooser est acquitté durablement ; un
redémarrage QuickShell dans la même session ne le réaffiche pas.

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
L’extension signée déjà installée n’a pas besoin d’être réinstallée pour ce nettoyage.

Versions de la recette : Firefox 157.0, SwayFX 0.6, QuickShell 0.3.1,
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
python3 -B -m unittest discover -s tests/session_v2 -p 'test_*.py'
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

## Limites conservées

- Contenu et processus terminal non restaurés.
- Ratios exacts non restaurés.
- Fullscreen et scratchpad non pris en charge actuellement.
- Multi-output physique non validé.
- Provider Firefox candidat actuel pour le profil supporté ; plusieurs profils
  simultanés ne sont pas pris en charge.
