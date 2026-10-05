# Thème selon le fond d'écran — 17D

`themeMode` dans `$XDG_CONFIG_HOME/labfy-appearance/preferences.json` vaut
`manual` ou `wallpaper`. `manualFlavor` conserve le dernier choix manuel pendant
Auto ; revenir à Manuel le restaure immédiatement. L'accent reste `lavender`.
`effectiveMode` décrit le rendu (`normal` en 17D), tandis que `themeMode` est la
stratégie utilisateur. `effectiveDark` vaut `false` uniquement pour Latte et
`effectiveHighContrast` reste `false`. Sun Mode aura priorité sur cette
stratégie dans un lot ultérieur, sans modifier les préférences manuelles.

Le backend `wallpaper-manager.py` expose `analyze FILE`, `set-theme-mode
manual|wallpaper`, `set-manual-flavor latte|frappe|macchiato|mocha` et `status`.
Chaque succès écrit un seul objet JSON sur stdout ; les erreurs vont sur
stderr avec un code non nul. `analyze` ne modifie aucun état effectif. La page
Thème appelle `AppearanceController`, qui sérialise les opérations. Le CLI
`generate-appearance.py --apply` délègue au même backend en mode Manuel.

## Algorithme 1

Pillow applique l'orientation EXIF et réduit l'image à **128 × 128 au plus**
avec LANCZOS. Les pixels transparents sont composités sur noir, ce qui rend
le résultat déterministe. Chaque canal sRGB normalisé `c` devient une valeur
linéaire `c/12.92` si `c <= 0.04045`, sinon
`((c+0.055)/1.055)^2.4`. La luminance est
`Y = 0.2126 R + 0.7152 G + 0.0722 B`.

Le backend calcule `mean`, `median`, `p10`, `p25`, `p75` et `p90` de Y dans
`[0,1]`. Le score est
`0.50 × median + 0.30 × mean + 0.10 × p25 + 0.10 × p75`.
La médiane limite l'effet d'une petite zone opposée ; les quartiles
distinguent les compositions mixtes d'une couleur uniforme de même moyenne.
Les seuils constants de l'algorithme 1 sont :

| Score | Flavor |
| --- | --- |
| `[0, 0.15)` | Mocha |
| `[0.15, 0.30)` | Macchiato |
| `[0.30, 0.64)` | Frappé |
| `[0.64, 1]` | Latte |

Ils ont été placés entre les groupes observés : gris 80 (`0.080`) / gris
128 (`0.216`), gradient (`0.257`) / fond Sway bleu (`0.367`), gris 192
(`0.527`) / gris 224 (`0.745`). Les fixtures noir, blanc, cinq gris,
gradient, moitié noir/blanc, 80 % sombre et 80 % clair sont générées dans un
dossier temporaire par les tests ; elles ne sont pas des fonds utilisateur.
La moitié noir/blanc donne un score voisin de `0.47` et Frappé ; les
compositions 80/20 donnent Mocha ou Latte selon la majorité. Les seuils ne
prétendent pas mesurer une préférence personnelle : ils rendent la règle
reproductible et révisable par version d'algorithme.

Mesures locales de calibration (arrondies, 4 octobre 2026) :

| Image | mean | median | p10 | p90 | score | Flavor |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Sway bleu 1920×1080 | .3718 | .3647 | .2291 | .5182 | .3672 | Frappé |
| 662412 blur 3200×1999 | .0122 | .0140 | .0011 | .0230 | .0124 | Mocha |
| 662412 original 3200×1999 | .0125 | .0139 | .0011 | .0240 | .0124 | Mocha |
| arch_rainbow 6024×3401 | .0107 | .0078 | .0059 | .0118 | .0087 | Mocha |
| sway 1440×900 | .0662 | .0569 | .0569 | .0725 | .0602 | Mocha |
| swaylock 1440×900 | .0688 | .0569 | .0569 | .0817 | .0615 | Mocha |

Le cache JSON se trouve dans `$XDG_CACHE_HOME/labfy-appearance/analyses/`.
Sa clé SHA-256 comprend version d'algorithme, chemin canonique, taille et
`mtime_ns`. L'écriture utilise temp/flush/fsync/replace. Un fichier changé
ou une version d'algorithme nouvelle force un recalcul. Au delà de 256
entrées, seul ce cache est réduit à 224, au moment d'une nouvelle analyse ;
aucun daemon ou polling n'est ajouté. Sur les fonds locaux, les analyses
non cachées observées ont duré environ 0,03 à 0,10 s pour 1080p/4K et
0,2 à 0,3 s dans le premier essai sur une grande image 6024×3401.

## Application et reprise

En Auto, l'image est décodée et analysée avant toute écriture. Le backend
prépare `generated/wallpaper.conf` et `generated/theme.conf` si nécessaires,
valide Sway, recharge Sway, confirme `swaybg`, puis écrit `effective.json`
schéma 3 et les préférences schéma 3 (depuis 17E) avant publication IPC QuickShell. Un
verrou non bloquant commun empêche deux applications simultanées. Si une
étape échoue, les anciens fichiers générés et JSON sont restaurés et Sway
est rechargé. Un échec d'analyse est signalé distinctement avant écriture ;
il ne retire pas un fond déjà appliqué. En Manuel, appliquer un fond ne
réécrit pas le thème. La sélection dans la galerie n'analyse rien.

Une transaction stricte entre fichiers, Sway et QuickShell n'existe pas.
Au démarrage, `status` considère `effective.json` comme dernier état publié
valide et répare les deux fichiers générés si une interruption les a laissés
en avance. Les schémas effectifs 1 et 2 migrent en conservant les champs et la
révision ; l'absence de préférences 17C initialise Manuel avec le flavor
effectif existant. Si l'analyse Auto manque ou change de version, `status`
la recalcule. Il ne remplace pas silencieusement un flavor appliqué par un
autre si le fichier a changé sur disque ; l'utilisateur réapplique ce fond
pour publier un nouvel état. La galerie et son dossier restent régis par
[`WALLPAPER.md`](../controlcenter/WALLPAPER.md).
