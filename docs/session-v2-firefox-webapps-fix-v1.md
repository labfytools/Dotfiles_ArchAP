# Firefox webapps et restauration V2 — 27 octobre 2026

## Incident réel

À 08:34, après une nouvelle connexion Sway, la tentative
`ab783694a02749a4ad65085e9a56186e` a échoué avec
`FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE`. Le rapport affiche `cleanup-error`,
mais les preuves montrent une résolution échouée suivie d'un nettoyage réussi :
5 applications observées sur 5, 7 slots attendus, 6 ancres créées et supprimées,
0 swap, helper suspendu/repris 1/1, reçu `recovered` sans problème.

Les origines enregistrées étaient celles des applications fraîchement lancées :
Firefox, ChatGPT et Kitty sur le workspace 1, WhatsApp sur 9, LiMusic sur 10.
La récupération a remis ces origines ; elle n'a pas appliqué le layout du
checkpoint. Cela explique les colonnes sur 1 et les autostarts correctement placés.

Le checkpoint de déconnexion de 08:33:18 est conservé. Aucune nouvelle sauvegarde
n'a été créée depuis la disposition issue de cet échec. Le nouvel incident a
remplacé le journal actif du 22 octobre ; l'ancien plan de retrait ne s'applique
pas à cette nouvelle transaction, déjà récupérée.

Archive de diagnostic privée :
`/home/fy59/.local/state/labfy-sway/session-v2-diagnostics/20261027-083749-firefox-provider`.

## Cause établie

L'extension signée 1.1.1 est active et son native host est vivant, sur le bon
socket Sway. L'absence de publication n'est donc pas une extension désinstallée.

Le code de Firefox 158.0.1 installé expose les Taskbar Tabs avec le type
WebExtension `normal`, mais SessionStore exclut ces fenêtres de ses états
persistants et des fenêtres récemment fermées. Une webapp créée avant Firefox
au login n'a donc pas l'UUID qu'elle pouvait posséder en mémoire auparavant.
La 1.1.1 valide tous les UUID avant la première publication : cette absence
bloque aussi le navigateur ordinaire. Avec des UUID déjà présents, l'ordre de
publication pouvait masquer le défaut lorsque Firefox était traité avant WhatsApp.

La consultation ciblée des seules métadonnées a confirmé que l'UUID Firefox du
checkpoint existe encore dans les fenêtres fermées / l'état précédent. Aucune
URL, aucun titre ni contenu d'onglet n'a été utilisé pour attribuer une identité.

## Correction

### Companion 1.1.2 et host

Le host ajoute `classify-window` avec un jeton de corrélation, sans UUID.
La réponse fermée distingue les app_ids exacts Firefox et WhatsApp du catalogue.
Une webapp positivement reconnue est exclue avant lecture, validation ou mint
UUID. Une fenêtre normale sans UUID reste refusée. Les classes inconnues,
collisions, réponses invalides, changements de classe/con_id ou changements du
lot restent refusés.

Le cache est borné, éphémère et invalidé sur close ; les captures et les mints
revalident les classes. Il n'y a pas de marquage périodique permanent en idle.
`map-window` reste réservé au navigateur ordinaire. ID d'extension, permissions,
clé de session et format des snapshots ne changent pas.

### Moteur et interface

L'admission résout le lot Firefox complet et ses UUID exacts après lancement,
mais avant Recovery, Guard, staging et ancres. Elle revalide ensuite identités,
emplacements, ordre et focus. Une indisponibilité à cette frontière est
`DEFERRED`, sans mutation de layout ni nouvelle tentative durable. Un UUID
sauvegardé manquant reste un échec exact. Les contrôles tardifs et la récupération
après erreur restent en place.

Le dialogue différencie cette attente de Firefox d'un refus de focus. Il propose
un nouvel essai explicite sans capturer le clavier et ne réessaie pas seul.

## Validation

- 68 tests JavaScript réussis, dont 10 nouveaux sur la classification.
- 30 tests host ciblés réussis, dont 10 nouveaux ; framing réel inclus.
- Suite Python : 121 tests réussis, dont 7 nouveaux d'admission.
- Deux scénarios headless supplémentaires : `natural` réussit avec 3 swaps ;
  `provider-placement` conserve son refus tardif après admission.
- Interface QML réelle en Sway privé : message Firefox, retry manuel disponible,
  pas de capture du focus ni d'acquittement mensonger.
- Firefox 158.0.1 réel, profil vierge, bus et Sway privés, webapp créée en premier :
  1.1.1 reproduit le refus ; 1.1.2 réussit la capture exacte. L'UUID du navigateur
  est inchangé et la webapp reste sans UUID. Cela valide aussi la propagation du
  préfixe de corrélation d'une vraie Taskbar Tab jusqu'à Sway.

Les tests réels sont reproductibles avec `tests/session_v2/firefox_webapp_runtime.py`
et `tests/session_v2/provider_ui.py`. Les seuls navigateurs lancés par ces tests
utilisent des profils vierges et des sockets privés. Le mode système Marionette
est réservé à ces navigateurs jetables, jamais au profil utilisateur.

Cette validation ne constitue pas un test physique de la prochaine déconnexion
et reconnexion de l'utilisateur.

## Paquet préparé et installation initialement attendue

XPI candidat 1.1.2 non signé, 6 935 octets, deux builds identiques :
`1e1b4a7a88694ff9eebda153d1ea347a2ae662ecadf40401f0a03002358fe95b`.
Il contient uniquement `manifest.json` et `background.js`.

Le host compatible peut être déployé avant l'extension et reste compatible avec
1.1.1. Le filtrage correct exige toutefois l'installation de 1.1.2 signée par
Mozilla, sous le même ID `session-v2@labfy.org`. Le paquet signé doit conserver
les mêmes deux sources ; les fichiers de signature sont ajoutés par Mozilla.
Aucune signature, publication AMO ni installation de l'extension utilisateur
n'a été effectuée pendant cette préparation.

Après signature et installation : vérifier les versions et la capture des UUID
attendus sans réécrire le checkpoint, puis effectuer une seule restauration
explicite surveillée. Ne pas inventer d'UUID, effacer les preuves ou réessayer
aveuglément une tentative échouée.

## Installation et essai réel vérifiés

L’utilisateur a installé la version **1.1.2 signée par Mozilla**. La vérification
locale confirme le même ID `session-v2@labfy.org`, active=true, signedState=2,
sans désactivation utilisateur ou applicative. Le background installé est
identique au candidat testé ; le manifest est sémantiquement identique, avec
les mêmes permissions. Les fichiers de signature ont été ajoutés par Mozilla.

SHA-256 du XPI signé installé :
`b1d9a9be10a8e0a4c865f7af106bdc27a47c9e2e206efd284111d19452b776d4`.

Après redémarrage du host natif, l’admission réelle a retrouvé l’UUID exact de
Firefox attendu dans le checkpoint, y compris avec WhatsApp présent. Le blocage
Firefox initial est donc résolu pour cette fenêtre et cette installation.

L’unique essai de restauration ensuite autorisé a révélé une autre erreur :
`RECOVERY_FOCUS_MISMATCH`, transaction
`475fac98b5234db0bddaded9cfe4198f`. Ce résultat ne constitue pas une restauration
réussie. Les deux clients déplacés ont été remis à leurs workspaces d’origine ;
le checkpoint et les preuves de l’incident restent conservés.

Voir `session-v2-focus-staging-fix-v1.md` pour la reproduction native, le
correctif et la reprise proposée. La preuve d’installation détaillée se trouve
dans `extension-installation.json`, sous le diagnostic privé
`20261027-102041-signed112-restore`.
