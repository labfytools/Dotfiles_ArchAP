# Capture annotée SwayFX V1

`Print` conserve la capture de zone rapide vers `wl-copy image/png`.
`Shift+Print` conserve la capture plein écran rapide. `Ctrl+Print` lance
`screenshot-region --annotate` : sélectionner une zone, puis annoter dans
Swappy. Échap pendant la sélection annule avant `grim` ; fermer Swappy annule
sans copie ni sauvegarde.
Avant `slurp`, les panneaux QuickShell Clipboard, Applications et Overview
ouverts sur la sortie focalisée sont fermés via leurs IPC, puis leur disparition
est attendue. Aucun workspace ni fenêtre utilisateur n'est déplacé.

Swappy 1.8.0 fournit flèche, rectangle, texte, pinceau, annulation et
rétablissement. Le panneau est ouvert au démarrage. `Ctrl+C` copie la version
annotée en `image/png` avec l'action native de Swappy ; `Ctrl+S` enregistre.
`early_exit=true` ferme l'éditeur après l'une de ces actions. Échap ou
`Ctrl+W` ferment sans sauvegarde. Pour masquer une information sensible,
utiliser un **rectangle plein opaque** (`f` pour remplir, transparence
désactivée), puis vérifier le résultat. Le flou n'est pas une garantie
d'effacement d'un secret.

La capture brute reste dans un répertoire privé `0700` propre à l'invocation
sous `XDG_RUNTIME_DIR`. Aucun `wl-copy` ne reçoit l'image brute dans ce mode.
Un verrou consultatif sur le répertoire runtime sérialise l'ouverture de
Swappy, application GTK à instance unique, lorsque deux raccourcis arrivent
presque ensemble ; il ne crée pas de fichier persistant.
Swappy reçoit le PNG directement et son bouton Copier appelle `wl-copy` avec
le type `image/png`. Les collecteurs cliphist restent inchangés ; une copie
Wayland réussie ne garantit pas l'archivage d'un PNG de plus de 5 000 000
d'octets dans la version installée de cliphist.

Le bouton Enregistrer écrit d'abord dans un dossier privé de cette invocation.
Après fermeture, le script vérifie le PNG et le publie sous un nom exclusif
`Screenshot-YYYYMMDD-HHMMSS-XXXXXXXX.png` dans `Screenshots` du répertoire
Images XDG. La configuration actuelle pointe vers `~/Pictures/Screenshots`.
Ce dossier n'est créé qu'après un enregistrement explicite. Le script nettoie
ses seuls fichiers temporaires à la fermeture, à l'annulation, en erreur et
sur interruption. `auto_save=false` et l'absence de `--output-file` sont
essentiels : Swappy 1.8.0 écrit cette sortie même lors d'une fermeture.

Dépendances : Swappy 1.8.0 (`sudo pacman -S swappy` sur Arch), GTK3, Cairo,
Pango, `wl-clipboard`, `grim`, `jq`, `flock` (util-linux), Python 3 et
`python-pillow`. Le script
utilise **`~/.local/libexec/labfy-slurp`** et non `/usr/bin/slurp` ; le
construire avec `tools/build-slurp-keymap-guard` si nécessaire. La règle de
fenêtre cible exclusivement `me.jtheoof.swappy`, identifiant déclaré dans le
code de Swappy 1.8.0. La bordure et les coins viennent de SwayFX ; le thème
GTK courant n'est pas modifié.

## Thème système

Le thème de Swappy suit la configuration GTK de la session, sans forcer
un nom de thème ni une variante sombre. Le répertoire `XDG_CONFIG_HOME`
temporaire reste propre à Swappy pour ses options d'annotation et de sauvegarde,
mais ses sous-répertoires `dconf` et `gtk-3.0` sont des liens symboliques vers
la configuration utilisateur originale (`$XDG_CONFIG_HOME`, sinon
`$HOME/.config`). Le thème, les icônes, la police et le CSS GTK restent ainsi
ceux du système ; ils ne sont pas copiés dans un instantané figé.

La suppression du répertoire temporaire retire uniquement ces liens, pas
les réglages utilisateur. Les chemins XDG avec espaces et l'absence de
réglages GTK explicites sont pris en charge. Aucune valeur `GTK_THEME`
n'est ajoutée : une éventuelle valeur déjà fournie par la session est
conservée, comme pour les autres applications GTK.

Le diagnostic a reproduit un retour à Adwaita clair sans ces liens, puis
retrouvé le même Catppuccin Mocha, les mêmes icônes et la même police que GTK
lancé normalement. Les tests isolés couvrent deux thèmes factices successifs,
un répertoire XDG personnalisé et la conservation des fichiers originaux.

Le test isolé `python3 -B -m unittest tests/test_screenshot_annotation.py -v`
utilise une image synthétique et de faux exécutables. Une vérification
graphique après installation de Swappy reste nécessaire : flèche, cadre,
texte, annuler/rétablir, collage de la copie après fermeture, enregistrement
explicite et fermeture sans enregistrement. Le test du presse-papiers réel ne
doit être lancé qu'avec l'accord de l'utilisateur, car il remplace son contenu.
