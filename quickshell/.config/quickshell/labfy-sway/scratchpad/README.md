# Tiroir de fenêtres SwayFX V1

Le tiroir utilise le scratchpad natif de SwayFX. `DrawerService.qml` conserve un
modèle partagé entre les sorties : un relevé `get_tree` au démarrage et après les
événements `window`, `workspace` ou `output` suffit. Aucun inventaire persistant
n'est créé. Les fenêtres Wayland (`app_id`) et Xwayland (`window_properties.class`)
sont identifiées par `con_id`. Le compteur inclut les membres masqués sous
`__i3_scratch` et les membres affichés sur un workspace ordinaire, reconnus
par `scratchpad_state`.

Dans `WindowStrip`, le menu de la fenêtre choisie propose **Ranger dans le
tiroir**. Le raccourci existant `Super+Ctrl+I` range le conteneur focalisé et
`Super+I` garde le cycle scratchpad natif ; aucun raccourci ni geste n'a changé.
L'indicateur Teal se place à gauche, immédiatement avant les workspaces et
après `Resize` lorsqu'il est actif. Il n'ajoute aucun séparateur et n'apparaît
que si le tiroir contient au moins une fenêtre. Son panneau s'ouvre sous
l'icône sur la sortie de la barre cliquée. Clic
pour ouvrir ou fermer ; flèches haut/bas pour choisir une entrée, gauche/droite
pour choisir l'action, Entrée pour exécuter, Échap pour annuler et rendre le
focus précédent.

**Afficher** déploie une entrée sur le workspace visible de la sortie de la
barre choisie et lui donne le focus ; si elle s'y trouve déjà, l'action se
limite au focus. **Masquer** la remet dans le scratchpad sans cycle. **Remettre
ici** retire son appartenance au scratchpad, la place sur ce workspace et
conserve le flottement. SwayFX garde l'appartenance après un simple `move` :
le retrait utilise `floating disable` puis `floating enable`, sans appliquer
de layout au workspace entier. L'ancienne place exacte dans la mosaïque n'est
pas restaurée. Une fenêtre rangée affichée reste comptée comme membre.

Les commandes ciblées relisent l'arbre avant et après, valident la fenêtre et
le workspace visible sur la sortie, puis vérifient l'état final. Les noms
contenant espaces, point-virgule ou un type de guillemet sont cités suivant
la grammaire Sway. Par prudence, les noms contenant `$`, un contrôle ou les
deux types de guillemets sont refusés. Les conteneurs multi-applications du
scratchpad sont visibles mais leurs actions individuelles sont désactivées.
Le menu n'ouvre pas et les commandes n'avancent pas durant Polkit. Une seule
opération est en vol dans QuickShell ; le backend ne dépend pas du focus du
client pour identifier la fenêtre. Le panneau possède une surface nommée
`labfy-scratchpad-drawer`, exclue des captures automatiques Overview.

Tests : `python3 tests/quickshell/test_scratchpad_drawer.py`,
`python3 tests/overview/test_backend.py`, `qmllint`, `git diff --check`.
Le cycle complet, les répétitions idempotentes, la sortie depuis l'état masqué,
la navigation clavier et le retour du focus ont été vérifiés avec Zenity
uniquement. Les comportements multi-écrans sont conçus autour du nom de
sortie mais n'ont pas été essayés physiquement.

Capture rapprochée du placement gauche avec une fenêtre Zenity synthétique
rangée et l'entrée déjà présente de l'utilisateur, sans déplacer cette dernière :
[quickshell-scratchpad-left-placement.png](../../../../../docs/assets/screenshots/quickshell-scratchpad-left-placement.png).

Retour arrière complet du tiroir : retirer l'intégration `DrawerService` de
`shell.qml`, les propriétés et callbacks `drawerService` de `Bar.qml` et
`WindowStrip.qml`, l'entrée de `WindowMenu.qml`, le namespace de
`overview/backend.py`, puis les nouveaux fichiers `scratchpad/` et
`status/DrawerIndicator.qml`. Les raccourcis Sway restent inchangés.
