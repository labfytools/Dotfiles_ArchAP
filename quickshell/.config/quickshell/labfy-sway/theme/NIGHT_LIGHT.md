# Lumière nocturne — 17E

La page **Réglages rapides → Apparence → Lumière nocturne** propose Désactivée,
Auto et Activée. `nightLightMode` est le choix persistant de l'utilisateur :
`off`, `auto` ou `on`. `effectiveNightLightMode` décrit le mode appliqué.
`nightLightSuspended` vaut `false` en 17E. Le futur Sun Mode pourra le mettre
à `true` et suspendre la correction sans modifier `nightLightMode` ; la
priorité prévue est Sun Mode > Night Light. 17E ne démarre pas Sun Mode.

Les préférences Appearance restent dans
`$XDG_CONFIG_HOME/labfy-appearance/preferences.json`, hors Git (schéma 3).
La migration conserve les champs 17D et ajoute `nightLightMode`,
`nightTemperature`, `dayTemperature`, `scheduleType=solar` et la position
locale. Les coordonnées historiques ont été migrées avant le changement de
l'unité systemd. Aucune géolocalisation distante n'est utilisée. Sur une
nouvelle installation sans position, le repli est Off et Auto indique
« Planification à configurer » ; aucune coordonnée n'est inventée.

Auto reprend exactement la planification solaire native de wlsunset 0.4.0,
avec la position locale, 3000 K la nuit et 6500 K le jour. Activée force la
température de nuit en permanence. La version locale refuse une température
haute égale à la basse ; le service démarre avec un horaire manuel valide,
puis `ExecStartPost` utilise deux SIGUSR1 documentés pour atteindre
`FORCE_LOW`. Le démarrage et chaque reprise du service réappliquent ce mode.
Désactivée arrête le service : la destruction du contrôle gamma Wayland par
wlsunset rend le contrôle au compositeur. La perception du retour neutre doit
être confirmée sur l'écran physique ; une capture ne contient pas forcément
la correction gamma.

`wlsunset.service` reste l'unique propriétaire du processus. Le launcher
`night-light-manager.py launch` lit les préférences validées, construit un
argv sans shell, puis `exec` `/usr/bin/wlsunset`. L'unité reste enabled pour
la prochaine session. En Off, le launcher quitte sans daemon et le backend
arrête l'unité dans la session courante. QuickShell n'est pas le daemon gamma :
son arrêt ou redémarrage ne coupe pas wlsunset. La commande `reconcile`
compare préférence, unité, PID et argv, répare une unité arrêtée en Auto/On
ou active en Off, et refuse une instance étrangère sans `pkill` global.

Le backend expose `current`, `validate`, `set-mode`,
`set-night-temperature` et `reconcile`, avec JSON sur stdout et erreurs sur
stderr. Une écriture de préférences passe par fichier temporaire, flush,
fsync et replace. Si l'application ou la publication échoue, le backend
restaure les JSON précédents et le service. Les températures de nuit admises
vont de 2500 à 5000 K par pas de 100 K ; l'interface applique la valeur avec
un bouton, sans relancer le service pendant le glissement. La température de
jour reste 6500 K en V1. Aucun polling de l'unité n'est effectué.

Changer la lumière nocturne ne modifie pas le thème, l'accent ou le fond
d'écran. Les champs effectifs ajoutés à `effective.json` ne prétendent pas
connaître la température instantanée pendant une transition wlsunset.
