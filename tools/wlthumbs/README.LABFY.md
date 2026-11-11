# wlthumbs — copie spécifique au dock Labfy

Source amont MIT : https://github.com/mil-ad/wlthumbs
Commit de référence : `516603c3144078b4d974108b80f7e9622ee4f3c9`
La licence MIT d'origine est conservée dans `LICENSE`.

**Différence intentionnelle :** un argument `-ids` obligatoire (1 à 8
identifiants `foreign_toplevel_identifier` hexadécimaux de 32 caractères),
avec liste blanche appliquée **avant** toute création de source de capture.
La capture des sorties complètes par `-outputs` est refusée dans notre version.
C'est une précaution essentielle : le dock ne doit jamais capturer toutes les
fenêtres quand l'utilisateur survole une seule application.

Ce programme ne surveille ni le bureau ni le pointeur. Il est lancé uniquement
à la demande par `bin/dock-thumbnails.py`, effectue une seule capture par fenêtre
autorisée, puis se termine.

Pour construire et installer dans le répertoire utilisateur :

```sh
~/.dotfiles/tools/build-labfy-wlthumbs.sh
```

Dépendances de compilation : Go (module déclaré dans `go.mod`, versions
figées dans `go.sum`). Pas de `sudo`, aucune modification de SwayFX, ni
de connexion réseau à l'exécution du programme compilé.

Voir `docs/quickshell-dock-window-previews-v1.md` pour les restrictions de
confidentialité, le cache temporaire et les tests.
