# Menu Applications

Le bouton Arch est le premier élément de la barre, avant Resize et les
workspaces. Il ouvre un `PanelWindow` layer-shell sur la sortie de la barre
cliquée, à 16 px du bord gauche et 12 px sous la barre. La carte mesure au plus
680 × 560 px logiques et se réduit aux dimensions disponibles. La surface ne
réserve aucune place dans Sway ; sa zone transparente absorbe le clic extérieur
jusqu'à la fin de l'événement souris. Le raccourci `Mod+Alt+L`, auparavant le
lanceur Wofi drun, choisit la sortie focalisée via
`~/.config/sway/scripts/applications-quickshell`. Les autres usages de Wofi et
Rofi restent en place. Une seule sortie possède le menu à la fois.

`ApplicationsMenu.qml` montre la recherche, une navigation par catégories et
une grille d'icônes. `ApplicationsModel.js` classe les entrées fournies par
`DesktopEntries.applications` ; l'événement `applicationsChanged` actualise le
catalogue après une installation ou désinstallation sans relancer Sway. La
recherche compare noms, noms génériques et mots-clés sans tenir compte des
majuscules et accents, dans toutes les catégories. Les catégories vides sont
masquées. Les icônes d'application conservent leur thème et leurs couleurs ;
une icône générique est utilisée en dernier recours. Le menu utilise les
couleurs du thème commun Catppuccin Mocha et donne le focus initial à la
recherche. `Tab` et `Shift+Tab` passent entre recherche, catégories et grille ;
les flèches choisissent, `Entrée` lance, `Espace` modifie le favori de la
sélection, `Échap` ferme.

Les favoris ordonnés sont enregistrés sous
`$XDG_STATE_HOME/labfy-sway/applications-favorites.json` (par défaut
`~/.local/state/labfy-sway/`), hors du dépôt. Le fichier privé (`0600`) ne
contient que la version et des identifiants `.desktop`. L'écriture est atomique
et protégée des mises à jour concurrentes. Au premier usage, Firefox, Kitty,
Yazi et Neovim sont proposés seulement si leurs entrées sont présentes. Une
liste existante n'est jamais écrasée ; les entrées désinstallées restent dans
l'état mais sont ignorées par la grille.

Le menu transmet uniquement un identifiant desktop validé à
`applications/backend.py`. Pour une entrée graphique ordinaire, ce helper
appelle `uwsm app -t service -- <identifiant>` afin de préserver l'intégration
de la session et de détacher l'application de QuickShell. Une entrée
`DBusActivatable` utilise `GioUnix.DesktopAppInfo.launch`. Pour `Terminal=true`,
le helper construit une entrée temporaire en mémoire et laisse Gio interpréter
`Exec`, ses arguments et codes de champ, ainsi que `Path` ; la commande est
encadrée par `uwsm app -t service -- kitty --`. Une entrée lançant déjà Kitty
ne reçoit pas de second terminal. Les véritables entrées `yazi.desktop` et
`nvim.desktop` ont été vérifiées dans Kitty. Le succès du helper confirme la
demande de lancement, sans prétendre qu'une fenêtre est déjà apparue.

Dépendances : QuickShell 0.3.1 avec `DesktopEntries`, Python 3 avec PyGObject
(`GioUnix`), UWSM, Kitty, Sway IPC, `jq`, `quickshell ipc`, la Nerd Font
existante et le thème d'icônes système. Aucune base de données ni daemon n'est
ajouté. Les limites : une seule sortie physique a été testée ; certaines
icônes peuvent manquer dans les thèmes installés ; le résultat d'une demande
UWSM ne garantit pas le démarrage complet de l'application. Les entrées
desktop masquées ou exclues par l'environnement sont aussi refusées par Gio au
moment du lancement.

Tests isolés : `python3 -B -m unittest discover -s tests/applications -p
'test_*.py' -v` et `node tests/applications/test_model.js` depuis la racine du
dépôt. `qmllint` vérifie le composant et la barre. Les tests du backend
emploient des entrées desktop synthétiques, sans lancer leurs commandes.
