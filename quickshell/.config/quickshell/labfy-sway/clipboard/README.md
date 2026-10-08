# Historique du presse-papiers

L'icône presse-papiers de la zone droite et `Mod+Alt+V` appellent la même fonction de la barre. Le raccourci passe par `~/.config/sway/scripts/clipboard-quickshell` et cible par IPC l'écran SwayFX focalisé. La barre crée `ClipboardPanel.qml` avec `LazyLoader` et le détruit à la fermeture. Le panneau reste une surface layer-shell à focus clavier exclusif, sans zone réservée ; sa carte est alignée sur la marge droite du Control Center, juste sous la barre. Elle mesure au plus 540 × 500 px et se réduit sur les petits écrans. Le focus revient à la fenêtre précédente quand la surface disparaît. Aucun démon supplémentaire ni interrogation permanente de `cliphist`.

Les collecteurs `cliphist-text.service` et `cliphist-image.service`, la base `cliphist` et la limite de **50 entrées affichées** restent inchangés. `backend.py` exécute directement `cliphist` et `wl-copy` sans shell. QML reçoit uniquement les aperçus de `cliphist list`, les identifiants et le type MIME. Avant une sélection ou une suppression, le helper vérifie que l'identifiant est toujours dans les 50 entrées courantes. `decode` doit terminer avec succès avant que `wl-copy` ne reçoive son flux binaire ; les images gardent leur type MIME.

La version installée de `cliphist` (0.7.0) ne fournit ni `list -fields` ni `max-store-size` : son code ignore sans erreur les entrées de plus de 5 000 000 octets. Un PNG plus grand peut donc être proposé par Wayland sans entrer dans l'historique. La limite n'est pas relevée implicitement. Une version ultérieure de `cliphist` expose ces options, mais une migration et son budget de stockage doivent être décidés séparément.

## Utilisation

- `↑` / `↓` : changer la sélection ; `Entrée` : restaurer l'entrée sélectionnée.
- Saisie directe : filtrer les textes ; les images restent visibles lorsque la recherche est vide.
- Clic gauche sur une entrée : restaurer et fermer ; défilement : parcourir.
- `Ctrl+Suppr` ou « Supprimer » : retirer l'entrée sélectionnée.
- « Tout effacer » demande une confirmation explicite ; « Annuler » et `Échap` l'annulent.
- `Échap`, un clic extérieur ou un second clic sur l'icône ferment le panneau. `Mod+Alt+V` le referme aussi.

L'ouverture du presse-papiers ferme Date Center, Control Center, le menu des fenêtres et le panneau des supports amovibles. L'ouverture de ces panneaux ferme réciproquement le presse-papiers. Les notifications ne sont pas modifiées.

## Images et confidentialité

Une seule image sélectionnée peut recevoir une miniature. Elle est produite par ImageMagick dans un répertoire `0700` sous `XDG_RUNTIME_DIR`, avec limites locales de mémoire et de surface. Le panneau nettoie ses miniatures à la fermeture. Les anciens fichiers de `cliphist/thumbs` ne sont pas réutilisés : leurs permissions et leur provenance ne sont pas garanties. Le décodage utilise un fichier temporaire privé, sans placer les octets binaires dans une propriété QML ou dans les arguments d'une commande.

Les journaux ne contiennent ni aperçu ni contenu décodé. L'interface affiche les aperçus seulement quand l'utilisateur l'ouvre. Elle ne crée pas de base supplémentaire ni de nouvelle politique de rétention. Les deux collecteurs actuels ne distinguent pas de manière fiable les secrets des autres contenus ; l'exclusion automatique des mots de passe n'est donc pas annoncée. Pour éviter la collecte d'un secret, il faut agir à la source ou définir ultérieurement une politique explicite.

## Dépendances et retour arrière

Dépendances : QuickShell 0.3.1, Qt 6, SwayFX, `jq`, Python 3, `cliphist`, `wl-clipboard`, ImageMagick et une Nerd Font. Le script Wofi `copypast` reste présent. Pour revenir à Wofi, remplacer uniquement la ligne `Mod+Alt+V` de `sway/.config/sway/bind` par `bindsym $mod+Alt+v exec ~/.config/sway/scripts/copypast`, puis recharger la configuration Sway. Les autres usages de Wofi, dont le lanceur `Mod+Alt+L`, restent indépendants.

## Vérification isolée

`python3 -B -m unittest discover -s tests/clipboard -v` utilise une base `cliphist` temporaire et le chemin absolu d'un faux `wl-copy`. Le test couvre texte, image PNG, octets, type MIME, suppression, purge, cache et historique vide. Il ne touche jamais l'historique personnel. Le panneau live est inspectable sans contenu via `quickshell ipc -c labfy-sway call clipboardUi-eDP-1 state` (adapter le nom de sortie).

`python3 -B tests/clipboard/ui_quickshell_smoke.py` exige une session Wayland et exerce les vrais `MouseArea` du panneau avec QtTest et la touche Entrée avec `ydotool` : icône, liste, texte, PNG, miniature, défilement, suppression, annulation et confirmation de purge, clic extérieur et focus. La base `cliphist`, le cache de miniatures et le faux `wl-copy` sont créés dans un répertoire temporaire privé. `CLIPBOARD_UI_CAPTURE=/run/user/$UID/clipboard-card.png` ajoute une capture intérieure de la carte factice pour vérifier le rendu.

`Print` passe par `screenshot-region` : il ferme d'abord le panneau exclusif s'il est ouvert, lance le `slurp` corrigé, puis confie la géométrie à `grim`. Échap arrête la commande avant toute écriture dans le presse-papiers ; seul un fichier PNG vérifié est remis à `wl-copy --type image/png`. Le binaire utilisateur `$HOME/.local/libexec/labfy-slurp` est construit par `tools/build-slurp-keymap-guard` depuis `slurp` 1.5.0, avec une garde sur les événements clavier reçus avant la keymap. La construction ne remplace pas `/usr/bin/slurp` et ne nécessite pas de privilèges administrateur.
Lorsque le paquet officiel inclura cette garde, remplacer le chemin utilisateur
dans `screenshot-region` par le binaire officiel et retirer la construction locale.

Pour une instance graphique de test, `LABFY_CLIPHIST_TEST_DB` désigne la base isolée et `LABFY_CLIPHIST_TEST_WL_COPY` le chemin absolu du faux `wl-copy`. Les deux variables doivent être fournies ensemble afin de ne toucher ni la base ni le presse-papiers de la session.

Limites : le filtre porte sur les aperçus textuels, pas sur le texte intégral ; les images ne sont pas recherchées. Une miniature ImageMagick peut être refusée par les limites de ressources sans empêcher la sélection de l'image. La surface prend le focus clavier seulement après sa création Wayland, environ 120 ms après ouverture.
