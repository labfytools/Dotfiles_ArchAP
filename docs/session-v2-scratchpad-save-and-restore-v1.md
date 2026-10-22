# SESSION_V2_SCRATCHPAD_SAVE_AND_RESTORE_V1

Travail local du 22 octobre 2026 dans
`labfy-session-v2-scratchpad-20261022`, branche
`feat/session-v2-scratchpad-20261022`, base `5aeff41d`.
Les correctifs focus/recovery préexistants restent présents. Aucun commit,
push, déploiement, reload QuickShell ou changement de configuration utilisateur.

## Résultat et fichiers

- `session_v2/snapshot.py`, `schema.py`, `schema-v2.json`, `model.py` :
  capture version 2, scratchpad `none/hidden/shown`, rectangle IPC, focus de slot
  et workspace focalisé explicite. Une fenêtre cachée a `workspace=null` ;
  l’espace interne `__i3_scratch` n’est jamais persisté comme workspace cible.
  Les groupes de fenêtres scratchpad restent refusés. Aucun titre ni argv
  n’est capturé. `schema-v1.json` reste inchangé.
- `layout.py`, `slots.py`, `executor.py`, `cli.py` : phase de placements
  descriptive, mapping conservant la visibilité des slots interchangeables,
  staging évité pour les scratchpads existants, commandes con_id ciblées,
  géométrie et état final vérifiés. Les nouvelles fenêtres arrivent par le
  prewarm existant, depuis le catalogue statique de confiance.
- `recovery.py` : nouveaux journaux version 2 avec appartenance scratchpad,
  lecture conservatrice des journaux V1, prédiction de focus avant chaque
  commande, refus d’une feuille dont la commande affecterait un ancêtre
  scratchpad non admis. Aucun conflit ni pending n’est effacé pour progresser.
- `controlcenter/SessionExitGate.qml` : `reason` JSON visible, explications,
  action de sortie toujours bloquée après échec jusqu’à un choix humain.
  Le ControlCenter fournit déjà ce JSON ; le diagnostic se perdait dans Gate
  qui privilégiait le stderr générique.
- `tools/build-session-v2.py` : inclusion des deux schémas dans le bundle.
- Tests : `test_scratchpad.py`, `scratchpad_runtime.py`,
  `validate_scratchpad.py`, extension de `qml/tst_exit_v2.qml`.

Les fonctions existantes `Guard.prepare`, les frontières de vérification finale,
la normalisation canonique des chemins et les tests focus/recovery initiaux
sont conservés. Le présent delta ne change pas la politique d’autotiling.

## Preuves et couverture

Le SwayFX installé échoue au démarrage headless dans ce sandbox faute de DRM.
Un paquet Sway 1.12 Arch a été extrait sous `/tmp/labfy-scratchpad-tool`, sans
installation système ni substitution de bibliothèque. `ldd` résout son
`libwlroots-0.20.so` installé sans dépendance manquante. Son renderer Pixman a
permis la campagne privée. Provenance :
[paquet Arch](https://archlinux.org/packages/extra/x86_64/sway/).
La prédiction du nouvel ajout scratchpad est étayée par le
[code Sway 1.12 root.c](https://github.com/swaywm/sway/blob/1.12/sway/tree/root.c)
et les observations privées : l’ajout initial refocalise le workspace source,
même si la cible était inactive. Le
[code scratchpad.c](https://github.com/swaywm/sway/blob/1.12/sway/commands/scratchpad.c)
explique également pourquoi `scratchpad show` est un toggle à ne jamais
émettre sans preuve de visibilité préalable.

La suite backend comprend 83 tests, dont 12 nouveaux tests scratchpad :

- capture/relecture déterministes, Store nommé et checkpoint automatique
  temporaires, compatibilité des snapshots V1 ;
- Kitty caché + autre Kitty visible, montré et focalisé, plusieurs cachés,
  workspace vide focalisé, splits et flottants ;
- références, types et versions stricts, JSON Schema V2, focus caché interdit ;
- scratchpad modifié entre lectures, fausse identité PID, output déplacé,
  focus ambigu, intention interrompue conservée et groupe non admis ;
- mapping sans exposition d’un pair caché et prédiction de focus avant IPC.

Autres suites : 29 tests focus Python, 13 tests QML via PySide6, 6 résultats
QtTest (4 tests métier et initialisation/nettoyage). Les tests QML vérifient
notamment `CAPABILITY_UNSUPPORTED`, `SNAPSHOT_CHANGED`, `RECOVERY_REQUIRED` et
un code inconnu, avec zéro commande de sortie après échec.

La campagne `scratchpad_runtime.py` utilise des Kitty réels uniquement sous
le socket enfant privé. Elle conserve arbres JSON et PNG avant/après :

1. deux Kitty du même app_id (un caché et un en split), un scratchpad montré,
   un flottant ordinaire et un autre split ;
2. capture, Store temporaire, perturbation puis restauration ; égalité exacte
   des géométries et états, focus final vérifié ;
3. show/hide explicite après restauration, sans perte d’appartenance ;
4. reconstitution de l’appartenance depuis des fenêtres ordinaires ;
5. toutes les fenêtres cachées et workspace vide focalisé ;
6. disparition puis relancement réel des deux Kitty par le catalogue statique
   TEST_ONLY, restauration cachée et second apply sans double lancement.

Les PNG avant/après de la campagne privée ont été inspectés. Ils montrent le
même arrangement ; ce sont des terminaux synthétiques noirs exécutant `sleep`,
pas une preuve de contenu applicatif ou d’une session utilisateur physique.
La trace de commandes vérifie qu’aucun move vers un workspace ni `scratchpad
show` ne cible la feuille destinée à rester cachée pendant le premier apply.

Régressions privées supplémentaires retenues sous
`/tmp/labfy-scratchpad-regressions-mivwhgzo/` : scénario Limusic V1 et refus
absent/dupliqué ; quatre scénarios de stabilité des chemins ; huit scénarios
login/focus (normal, workspace vide, fenêtre tierce, deux focus tardifs,
map dans le gap IPC, placement provider, crash en milieu d’intention).
Tous ont leurs succès ou refus attendus. Seul le nettoyage du harness a été
adapté dans un wrapper temporaire pour ne jamais envoyer SIGCONT.

Aucun scénario envoyant réellement SIGSTOP/SIGCONT à autotiling n’a été
exécuté. Son protocole est testé par simulation ; les tests headless réels
utilisent Guard sans autotiling. Aucun socket utilisateur ni fichier sous
`/run/user/1000/labfy-sway` n’est utilisé par les validations.

## Limites assumées

- **Enregistrer Kitty ne ressuscite pas btop.** Le processus interne, la commande,
  le titre et le contenu du terminal ne font pas partie du snapshot. Le lancement
  de production reste `/usr/bin/kitty` issu du catalogue. Le `sleep` du test vient
  exclusivement d’un catalogue statique TEST_ONLY, jamais des données capturées.
- Les slots de même application sans provider exact restent interchangeables,
  sans promesse de retrouver le rôle sémantique d’un terminal particulier.
- Les groupes scratchpad, fullscreen et géométries refusées par le client ou
  le compositeur produisent un échec précis, pas un succès partiel.
- Pour une feuille cachée, le rectangle sauvegardé est le rectangle IPC caché.
  L’ancienne transformation d’output interne à Sway n’est pas persistée. Un
  futur `show` manuel peut adapter ses coordonnées à l’output alors actif.
- Le `show` intermédiaire d’une feuille explicitement montrée laisse Sway
  convertir le rectangle à l’output ; la géométrie sauvegardée est ensuite
  appliquée et vérifiée exactement. Le délai de 300 ms des transitions Wayland
  ne remplace aucune preuve. Une modification tardive reste refusée.
- Une reprise après incident ne reconstruit pas automatiquement un scratchpad
  dont le placement diffère de l’origine prouvée : reçu
  `SCRATCHPAD_RECOVERY_REQUIRES_REVIEW`, fenêtres et journal conservés.
- Pas de validation de login physique, de multi-output physique, de SwayFX avec
  DRM, ni de contenu Firefox/btop. Les contrôles IPC ne constituent pas un CAS.
- Aucun nouveau checkpoint réel n’a été écrit. L’ancien état utilisateur
  `RECOVERY_REQUIRED` demeure bloquant ; ce patch ne l’acquitte pas.

## Reproduction sûre et future validation

Depuis ce worktree, avec un binaire Sway compatible disponible :

```sh
python -B tests/session_v2/validate_scratchpad.py \
  --sway /tmp/labfy-scratchpad-tool/usr/bin/sway --renderer pixman
```

Le validateur crée ses HOME/XDG sous `/tmp`, retire les variables graphiques
héritées et lance exclusivement un compositeur headless avec configuration
TEST_ONLY. Il conserve les logs et le chemin des arbres/PNG dans son répertoire
de résultats. Aucun accès privilégié n’est requis. Les clients et compositeurs
enfants sont arrêtés par le nettoyage du laboratoire ; aucun signal de
suspension/reprise n’est envoyé.

Pour la future recette humaine : examiner d’abord le diff et les preuves
privées ; reproduire avec plusieurs fenêtres de terminal identifiables et un
scratchpad montré/caché dans un compositeur privé. Toute recette sur le bureau
réel exigera une autorisation séparée et la résolution humaine préalable du
journal ancien. Ne pas effacer ce journal pour débloquer apply, ne pas tester
via logout/reboot et ne pas recharger QuickShell pour cette vérification.
Vérifier séparément la sauvegarde d’une fenêtre Kitty et l’absence de promesse
sur le redémarrage de btop.


## Résultats finaux conservés

- Validateur reproductible : `/tmp/labfy-scratchpad-validation-imopv2no/` ;
  tous les codes retour sont zéro (backend, focus, QML Python/Qt, runtime,
  diff-check).
- Campagne réelle finale : `/tmp/labfy-session-v2-TEST_ONLY-1gtxan7m/` ;
  snapshots, arbres, commandes, résultats, PNG avant/après/show/hide,
  nouvelles appartenances, toutes cachées et lancement Kitty à froid.
- Bundle local candidat : `/tmp/labfy-scratchpad-final-evidence/bundle/` ;
  compilation C17 stricte, schémas V1/V2 embarqués, non installé/non signé.
- Relecture locale du delta et vérification des patches initiaux : les diffs
  initiaux hors executor/recovery restent identiques octet pour octet ; dans
  ces deux fichiers, les mécanismes initiaux sont conservés et les suites de
  non-régression passent. Cela ne remplace pas la revue humaine avant commit.
- `qmllint` du composant Gate, parsing AST Python, contrôle des deux JSON
  Schemas et `git diff --check` : succès.
- Paquet Sway de test, SHA-256 :
  `5704cfc9eba9804116c665cb4450352bf5a240c1a8300b36aca3218116648443`.


### Revue complémentaire du focus de layer-shell

Le dialogue de sortie QuickShell peut rendre le focus de GET_TREE non
observable. Dans ce cas, le snapshot V2 garde explicitement
focus=null et focus_workspace=null, sans inférer de fenêtre depuis les
piles internes. Plusieurs noeuds simultanément marqués focused restent
refusés avec SNAPSHOT_FOCUS_AMBIGUOUS. Les tests vérifient cette
distinction et le round-trip du Store temporaire.
