# Appearance 17F — Mode Soleil

Le profil Soleil augmente la visibilité de QuickShell et SwayFX. Il ne modifie
ni le fond d'écran, ni la luminosité, ni les thèmes GTK, Qt, Kitty, Neovim et
Firefox. Ces cinq familles d'applications relèvent obligatoirement de 17G ;
17F ne constitue donc pas une intégration complète du bureau clair.

## État et priorité

`preferences.json` et `effective.json` utilisent le schéma 4. Les anciennes
préférences migrent vers `sunMode=false`, `sunVariant=light`,
`sunDarkFlavor=mocha`. Seuls `frappe`, `macchiato` et `mocha` sont admis pour
`sunDarkFlavor`. Les coordonnées Night Light restent locales et intactes.

`themeMode`, `manualFlavor` et `wallpaperAnalysis` décrivent le choix normal.
La résolution centrale calcule d'abord ce flavor normal, puis applique la
priorité Soleil : `sun-light` donne Latte ; `sun-dark` donne
`sunDarkFlavor` ; Soleil désactivé restitue le flavor normal. Aucun instantané
des préférences normales n'est utilisé. `effectiveDark` dérive du flavor,
`effectiveHighContrast` vaut exactement `sunMode`, et `effectiveAccent` reste
Lavender. `effectiveMode` vaut `normal`, `sun-light` ou `sun-dark`.

Une modification effective du profil ou du flavor augmente `revision` une
fois. Un changement de `sunDarkFlavor` lorsque Soleil est désactivé est
persisté sans révision visuelle. Les consommateurs 17G devront utiliser
`effectiveFlavor`, `effectiveAccent`, `effectiveDark`,
`effectiveHighContrast`, `effectiveMode` et `revision` comme source unique.
Un futur `AppThemeSynchronizer` distribuera cet état à ses adaptateurs GTK,
Qt, Kitty, Neovim et Firefox ; aucune logique spécifique à ces applications
n'appartient à `Theme.qml`.

## Transaction et reprise

`wallpaper-manager.py` tient le verrou Appearance commun. Il résout l'état,
écrit atomiquement `generated/theme.conf` et éventuellement
`generated/wallpaper.conf`, valide Sway, recharge SwayFX, vérifie le fond si
nécessaire, publie `effective.json`, réconcilie le service Night Light,
réapplique les opacités existantes par `--refresh`, écrit les préférences,
puis publie l'état QuickShell via IPC. En cas d'échec, il restaure les octets
précédents des fichiers et de l'état, recharge Sway, rétablit Night Light et
les opacités, puis renvoie une erreur. Les transitions sont sérialisées ; les
contrôles QML attendent la fin de la transaction.

Le listener d'opacité lit l'état uniquement à chaque événement fenêtre ;
`--refresh` lit une fois lors d'un changement de profil. Normal utilise
focused `1.0`, inactive `0.85` ; Soleil utilise `1.0` pour les deux. SwayFX
consomme les variables du générateur dans son unique bloc `layer_effects` :
blur de la barre `enable` en normal, `disable` en Soleil. Le rayon d'ombre
passe de 10 à 4 et les couleurs d'ombre sont renforcées en Soleil. Les
bordures restent de 2 px.

Le lanceur de `wlsunset.service` lit `effective.json` avant tout démarrage :
en Soleil, il ne lance pas de correction gamma. La préférence Off, Auto ou On
reste intacte ; en sortie de Soleil le service est réconcilié selon cette
préférence. Au redémarrage de QuickShell, Appearance se réconcilie avant Night
Light et reprend la révision persistée. Le repli versionné Mocha reste valide
sans fichiers générés.

## Contraste et limites

La barre QuickShell passe de `235/255` en normal à `1,0` en Soleil ; les popups
restent opaques (`1,0`) dans les deux profils. Les rôles `border`,
`strongBorder`, `outline`, `emphasisBackground`, `separator`,
`buttonBackground`, `buttonHover`, `secondaryForeground`, `inputBorder`
et `shadow` dérivent de la palette
Catppuccin et du contraste effectif. L'accent Lavender et `onAccent` suivent
le moteur 17B. Les ratios WCAG des paires principales sont :

| Flavor Soleil | texte/panel | secondaire/panel | texte/popup | onAccent/accent | texte/input |
| --- | ---: | ---: | ---: | ---: | ---: |
| Latte | 7,06 | 7,06 | 7,06 | 6,60 | 5,17 |
| Frappé | 8,06 | 8,06 | 8,06 | 11,47 | 6,19 |
| Macchiato | 9,92 | 9,92 | 9,92 | 11,65 | 7,55 |
| Mocha | 11,34 | 11,34 | 11,34 | 11,74 | 8,69 |

La paire sélectionnée reprend `onAccent/accent`. Les bordures et séparateurs
sont décoratifs ; le seuil de texte AA de 4,5:1 ne s'y applique pas. Les
icônes colorées des applications dans le tray ne sont pas recolorées.
La lisibilité réelle en plein soleil exige une validation sur l'écran physique.
