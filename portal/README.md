# Yazi comme FileChooser du portail

Package GNU Stow : `stow -d ~/.dotfiles -t ~ portal`. Les fichiers actifs dans
`~/.config/xdg-desktop-portal/` et
`~/.config/xdg-desktop-portal-termfilechooser/` sont des liens Stow. La règle
SwayFX est dans le package `sway`.

## Dépendances

Arch Linux : `xdg-desktop-portal`, `xdg-desktop-portal-gtk`,
`xdg-desktop-portal-wlr`, `kitty`, `yazi`, `jq`, `swayfx`, `libinih`,
`libsystemd`, `meson`, `ninja` et `scdoc` pour une compilation complète. Le
backend retenu est
[`hunkyburrito/xdg-desktop-portal-termfilechooser`](https://github.com/hunkyburrito/xdg-desktop-portal-termfilechooser),
version 1.4.3, commit `bcb2387949e4eb38a35390ebf1693f92869e619d` dans
l'installation testée. Le paquet AUR
`xdg-desktop-portal-termfilechooser-hunkyburrito-git` existe aussi.

Cette machine utilise une installation Meson utilisateur sous `~/.local`, sans
changer les backends système. Les fichiers nécessaires sont
`~/.local/libexec/xdg-desktop-portal-termfilechooser`,
`~/.local/share/dbus-1/services/org.freedesktop.impl.portal.desktop.termfilechooser.service`
et `~/.local/share/xdg-desktop-portal/portals/termfilechooser.portal`.
La procédure de reproduction, conservée dans ce dépôt indépendamment du cache
de construction, est la suivante (sans l'exécuter pendant une simple publication) :

```sh
git clone https://github.com/hunkyburrito/xdg-desktop-portal-termfilechooser.git
cd xdg-desktop-portal-termfilechooser
git checkout --detach bcb2387949e4eb38a35390ebf1693f92869e619d
meson setup build --prefix="$HOME/.local"
meson compile -C build
meson install -C build
```

Contrôler ensuite les trois chemins ci-dessus et la configuration Stow de ce
dossier. Le dépôt source et le répertoire `build` sont temporaires et ne font
pas partie des dotfiles. Cette procédure installe uniquement dans le préfixe
utilisateur ; elle ne remplace aucun paquet système.
Après installation ou mise à jour du backend, recharger seulement
`xdg-desktop-portal.service` après avoir vérifié qu'aucune session de partage
d'écran ou requête portal n'est en cours.

## Routage et fenêtre

`FileChooser` utilise `termfilechooser`, `ScreenCast` et `Screenshot` utilisent
`wlr`, `Secret` utilise `gnome-keyring`, et les autres interfaces disponibles
gardent `gtk`. `XDG_CURRENT_DESKTOP=sway:wlroots:swayfx` sélectionne la
configuration utilisateur `portals.conf` avant les fichiers système propres à
Sway. Le wrapper lance Kitty avec `--class labfy-yazi-filechooser` ; SwayFX
flotte et centre uniquement cet `app_id`. Kitty calcule au lancement une taille
de 1000 × 650, bornée à la sortie SwayFX active avec une marge de 40 pixels.
La fenêtre reste redimensionnable et sur le workspace courant. Le thème Kitty
et le thème Yazi Catppuccin Mocha sont ceux de la configuration habituelle.

Firefox 157 utilise le portail FileChooser en mode automatique quand il est
disponible. Aucun `GTK_USE_PORTAL` global ni préférence de profil n'est
nécessaire dans cette installation. Pour diagnostiquer un profil différent,
vérifier `widget.use-xdg-desktop-portal.file-picker` dans `about:config` : `1`
force le portail, `0` le désactive, `2` suit le mode automatique.

## Utilisation

Dans le sélecteur, `o` ou `Entrée` valide le ou les fichiers survolés ou
sélectionnés. `Espace` sélectionne chaque fichier en mode multiple. `q` annule
un choix de fichier ; `Q` annule aussi et ne transmet pas le dossier courant.
Pour un dossier, entrer dedans puis appuyer sur `q` ; `Q` annule. `M` ouvre le
menu des supports, `g` puis `Espace` permet de saisir un chemin. Ouvrir un
fichier via Yazi sans mode chooser n'est pas la même opération : ici, le
wrapper utilise `--chooser-file` pour remettre les chemins à l'application.

Pour « Enregistrer sous », le backend crée un fichier provisoire annoté. Le
déplacer avec `x`, naviguer vers la destination, le déposer avec `p`, puis le
renommer avec `r` si nécessaire. Valider le fichier avec `o` ou `Entrée`, puis
répondre `o` au prompt de confirmation du wrapper. Le prompt avertit que
l'application peut écraser une destination existante ; répondre autrement
annule. `Q` dans Yazi annule également et le backend supprime le provisoire
resté à son emplacement d'origine. Si le provisoire a été déplacé avant une
annulation, supprimer manuellement ce fichier déplacé. Les essais doivent
utiliser un dossier temporaire et éviter tout écrasement de données réelles.

Les applications GTK/Qt qui utilisent leurs dialogues natifs plutôt que le
portail conservent leur comportement. Ce réglage ne change aucune association
MIME et ne remplace pas les portails d'autres interfaces.
