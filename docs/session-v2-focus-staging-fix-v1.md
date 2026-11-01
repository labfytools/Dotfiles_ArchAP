# Focus pendant le staging et catalogue installé — 27 octobre 2026

## Incident réel conservé

Après installation vérifiée de l’extension Firefox signée 1.1.2, l’admission a
retrouvé l’identité exacte de la fenêtre Firefox enregistrée. Sept fenêtres
attendues étaient présentes. L’unique essai réel autorisé a ensuite échoué avec
`RECOVERY_FOCUS_MISMATCH`, transaction `475fac98b5234db0bddaded9cfe4198f`.

Deux déplacements avaient été exécutés, aucune ancre créée et aucun slot
reconstruit. Au déplacement de ChatGPT 16, le moteur attendait le conteneur
interne 32 ; Sway a focalisé le terminal 58. Le journal conserve cette divergence.

Les deux clients déplacés par cet essai, Kitty 37 et ChatGPT 16, ont été ramenés
séparément au workspace 1 après vérification de leurs identités et de leurs
origines. Le stage est vide. Cette remise en place n’est ni une restauration
réussie du checkpoint ni un rollback structurel complet. Le journal reste
`required` et son reçu `RECOVERY_REQUIRED`.

Le checkpoint de 08:33:18 est inchangé :
`9a36bb310f48d989a8763092ae220a974a00786da6fba2c86dc25e7cfed1cd89`.
Il décrit ChatGPT et deux Kitty sur 1, Firefox sur 2, WhatsApp sur 9, LiMusic
sur 10 et un troisième Kitty dans le scratchpad caché.

## Cause vérifiée sur SwayFX réel

Les listes de focus du JSON IPC donnent l’ordre des enfants directs.
La recherche interne de focus inactif examine une pile globale de descendants
de toute profondeur. Cette information globale ne peut pas toujours être
reconstruite depuis le seul arbre public.

Deux historiques synthétiques, exécutés avec le binaire installé SwayFX 0.6,
ont produit exactement le même arbre public, listes de focus comprises.
Le déplacement de la même feuille focalisée a néanmoins choisi un conteneur
interne dans un historique et une feuille dans l’autre. Le focus sur un
conteneur interne est donc légitime ; le remplacer systématiquement par une
feuille casserait l’autre cas.

Cette preuve établit le défaut de prédiction de cette transition. Elle ne
prétend pas reconstituer l’historique caché précis du bureau réel.

Sources locales vérifiées au tag 0.6 :
`sway/ipc-json.c`, `sway/input/seat.c`, `sway/commands/move.c` et
`sway/tree/workspace.c`, dans
`/home/fy59/Documents/Development/swayfx-mosaic`.

## Correction

Le moteur déplace d’abord les feuilles hors du sous-arbre focalisé, puis celles
de ce sous-arbre, en conservant l’ordre relatif de chaque groupe. Si la branche
focalisée doit disparaître, toutes les feuilles de son workspace source doivent
pouvoir être stagées. Un client étranger ou un scratchpad montré qui resterait
en place entraîne un refus préalable.

Cette admission s’applique aussi aux workspaces sources absents du checkpoint.
Elle passe avant tout journal transactionnel et est répétée après Guard. Le
contrôle du lot déjà admis garde la priorité : une nouvelle fenêtre apparue
après capture reste `APPLICATION_MEMBERSHIP_CHANGED`.

Le nouveau refus `RESTORE_FOCUS_STAGING_UNPROVEN` est différé uniquement en
phase 0. Après ouverture de la transaction, il reste une erreur transactionnelle.
L’interface fournit une explication et un nouvel essai manuel. Aucun retry
automatique ni déplacement forcé du focus n’a été ajouté.

Le prédicteur et tous les contrôles stricts de `recovery.py` restent inchangés.
Les focus sur workspace, client étranger ou conteneur interne conservant un
descendant sont préservés.

## Catalogue des applications

Le catalogue découvre maintenant les lanceurs installés avec GIO. L’inventaire
de cette machine contient 103 entrées, dont 95 cataloguées : 6 politiques
explicites et 89 entrées découvertes. Les métadonnées NoDisplay et OnlyShowIn
ne sont pas assimilées à une absence d’application.

La nouvelle stratégie V2 ouvre au plus une instance absente, puis attend toutes
les fenêtres enregistrées avant le moindre déplacement. Elle ne promet pas de
rouvrir les documents ni les commandes d’un terminal. Les identités ambiguës
restent refusées. Firefox conserve son provider exact.

Voir `session-v2-installed-app-catalog-v1.md` pour la politique complète,
les huit exclusions motivées et les limites de l’inventaire.

## Validation

- Suite Python intégrée finale : **150 tests réussis en 16,473 s**.
- 10 nouveaux tests de staging, 16 de catalogue et 3 pour Proton Pass.
- Aucun résultat attendu des tests existants n’a été assoupli. Le contrôle
  intégré a permis de corriger deux régressions : racine synthétique sans ID
  et priorité du refus d’un changement de lot après capture.
- Ancien moteur sur la reproduction imbriquée : échec attendu après deux
  déplacements, avec `RECOVERY_FOCUS_MISMATCH`.
- Nouveau moteur sur la même reproduction : succès, quatre slots et quatre
  swaps vérifiés, arbre/focus conformes, journal complete, aucune ancre ni
  fenêtre restant au stage, client étranger conservé.
- Variante avec focus initial interne : succès.
- Source avec client étranger restant : refus avant toute commande et sans
  journal/tentative.
- Cas existants preserve-empty-workspace et preserve-foreign : succès.
- Injection focus-helper-late : le refus strict après swaps reste présent.
- Deux historiques avec arbre IPC identique : focus natifs distincts démontrés.

Ces essais utilisent des sockets Sway privés et des clients synthétiques.
Ils ne constituent pas la validation d’une nouvelle restauration du bureau réel.

## Reprise préparée avant autorisation

Les preuves privées se trouvent dans :
`/home/fy59/.local/state/labfy-sway/session-v2-diagnostics/20261027-102041-signed112-restore`.

La dernière observation contient cinq survivants : LiMusic 7, ChatGPT 16,
Kitty 37, Proton Pass 46 et WhatsApp 62. Firefox 50 et Kitty 58/60 sont observés
absents ; leur fermeture n’est attribuée à aucune action particulière.

Le plan nominatif `retirement-current-plan.md` concerne uniquement la
transaction ci-dessus. Il propose d’archiver les trois fichiers actifs exacts,
avec copies persistantes et contrôles d’identités, de session, d’inactivité et
d’empreintes. Le reçu distinct doit porter `retired-after-manual-return`,
jamais une réussite automatique fictive.

Le helper est en dry-run par défaut. Sa fixture privée vérifie les renommages
et leur retour en cas d’échec ; son dry-run réel a réussi sans modifier les
fichiers protégés. Le retrait réel et un nouvel essai exigent l’autorisation
distincte prévue par `session-v2-focus-recovery-fix-v1.md`.

Une future restauration devra retrouver la fenêtre Firefox avec son UUID
enregistré, préparer les fenêtres manquantes, puis prouver les postconditions.
Ne pas remplacer le checkpoint par la disposition partielle actuelle.

## Validation réelle après autorisation — 12:10:59

L’utilisateur a autorisé le retrait nominatif de la tentative échouée et un
unique nouvel essai. Le helper a archivé les trois fichiers exacts sous
`/run/user/1000/labfy-sway/retired-475fac98b5234db0bddaded9cfe4198f`, en conservant
leurs copies persistantes et le statut distinct `retired-after-manual-return`.

Les deux terminaux manquants ont été ouverts. Le lancement normal de Firefox a
réouvert sa dernière fenêtre fermée, dont les métadonnées portaient l’UUID
attendu ; le provider a confirmé cette même identité sur le conteneur 79.
Aucune modification d’UUID ni réécriture de la session Firefox n’a été effectuée.

L’unique nouvel essai a réussi, transaction
`335bf44840674810b4761ade767f31db` : 7/7 slots, 6/6 ancres créées, échangées et
nettoyées, helpers suspendus/repris 1/1, arbre et focus vérifiés, recovery
`complete` sans issue. Un contrôle indépendant après l’essai a confirmé :

- workspace 1 : ChatGPT à gauche, deux Kitty empilés à droite ;
- workspace 2 : Firefox, avec l’identité exacte attendue ;
- workspace 9 : WhatsApp ; workspace 10 : LiMusic ;
- troisième Kitty caché, géométrie conforme au checkpoint ;
- Proton Pass étranger inchangé ; aucun stage ni aucune ancre restante.

Une capture réelle supplémentaire a réussi avec huit fenêtres et six
applications, dont Proton Pass. Elle est conservée uniquement dans le dossier
de diagnostic et n’a pas remplacé le checkpoint automatique d’origine.
L’acquittement `restored` a été enregistré après ces preuves ; startup-status
indique aucun essai en cours, différé ou interrompu.

Preuves privées :
`/home/fy59/.local/state/labfy-sway/session-v2-diagnostics/20261027-120604-focus-catalog-restore`.
Le checkpoint d’origine conserve son SHA-256 `9a36bb310f48d989a8763092ae220a974a00786da6fba2c86dc25e7cfed1cd89`.
Cette validation porte sur une restauration réelle dans la session active ;
aucune nouvelle déconnexion/reconnexion n’a été déclenchée pour ce contrôle.
