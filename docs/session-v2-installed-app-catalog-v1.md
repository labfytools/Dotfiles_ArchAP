# Catalogue des applications installées — session V2

## Changement demandé

Le 27 octobre 2026, l'utilisateur a demandé de prendre en charge les applications
installées, au lieu d'ajouter une entrée à chaque erreur
`APPLICATION_UNSUPPORTED`. Le catalogue explicite reste prioritaire pour
Firefox, WhatsApp, Kitty, ChatGPT, LiMusic et Proton Pass. La découverte des autres
applications complète ces politiques ; elle ne remplace aucune identité exacte
Firefox et ne modifie aucun checkpoint existant.

## Découverte et identité

`Catalog()` utilise `Gio.AppInfo.get_all()` et les objets `DesktopAppInfo`.
GIO applique la recherche XDG, y compris les installations locales et les exports
Flatpak, ainsi que la priorité des fichiers utilisateur et les overrides
`Hidden=true`. Une entrée non affichée dans le menu (`NoDisplay` ou
`OnlyShowIn`) peut toujours produire une fenêtre : elle reste admissible.

L'entrée doit être de type `Application`, avoir un ID compatible avec le
schéma, un fichier desktop régulier lisible appartenant à root ou à l'utilisateur
sans écriture groupe/autres, et un exécutable disponible ou une activation DBus.
Le catalogue ne lance rien pendant sa construction.

La correspondance des surfaces reste exacte et sensible à la casse :

- Wayland : nom du fichier desktop sans `.desktop` en priorité, puis
  `StartupWMClass`, puis nom d'exécutable non partagé.
- X11 : namespace typé `x11-class:`, `StartupWMClass` explicite prioritaire,
  puis noms exacts issus de l'entrée.
- Une identité de même priorité revendiquée par plusieurs entrées est retirée
  de toutes ces entrées ; aucun ordre alphabétique ne tranche une ambiguïté.
- Les namespaces des politiques explicites sont réservés dans les deux
  protocoles. Une entrée générique ne peut pas contourner le provider Firefox.
- Les noms d'interpréteurs/launchers communs (`env`, `flatpak`, `java`,
  `python3`, `AppRun`, etc.) ne servent pas d'identité.

Aucun titre, contenu de document, argument du processus ou URL d'onglet ne sert
au classement. Une application qui ne publie aucune de ces identités reste
refusée ; un catalogue de lanceurs n'est pas une preuve que chaque application
émet l'identifiant attendu dans toutes ses versions.

## Lancement et sauvegarde

La stratégie V2 `application-self-restore` autorise au plus une demande
d'ouverture si aucune fenêtre de l'application n'est déjà présente. Elle utilise
`/usr/bin/gio launch <fichier-desktop-installé>`, avec le chemin issu du
catalogue, après revalidation de l'identité et du contenu du fichier. Aucun
exécutable, chemin de document ou argument ne provient du snapshot.

Le moteur attend le nombre complet de fenêtres sauvegardé avant le premier
déplacement. Si une application rouvre une seule fenêtre sur les deux attendues,
la restauration est reportée avec `APPLICATION_WINDOWS_INCOMPLETE`, sans
staging, sans journal de récupération nouveau, ni seconde ouverture au retry
tant que la première fenêtre existe. La présence de toutes les fenêtres permet
ensuite la restauration de leur disposition selon le contrat existant.

Une fenêtre générique unique conserve l'identité singleton. Plusieurs fenêtres
de la même application restent interchangeables sans provider dédié : leurs
documents et commandes ne sont pas sauvegardés, et leur association individuelle
à chaque contenu n'est pas garantie. Le schéma V1 et les stratégies existantes
restent inchangés ; la nouvelle stratégie n'est acceptée qu'en V2.

Les applications `Terminal=true` sont des contenus de terminal, pas des surfaces
indépendantes. Le contrat Kitty restaure les fenêtres, pas les commandes qui y
tournaient. Les nouveaux lanceurs `firefox.webapp-*` non couverts par la politique
explicite restent `provider-required` tant que leur exclusion du provider Firefox
normal n'est pas établie.

## Inventaire de la machine le 27 octobre 2026

Lecture seule dans l'environnement de la session graphique :

| Résultat | Nombre |
| --- | ---: |
| Entrées installées vues par GIO | 103 |
| Entrées du catalogue | 95 |
| Politiques explicites | 6 |
| Entrées découvertes automatiquement | 89 |

Huit entrées sont exclues du catalogue de surfaces :

| Entrée | Motif |
| --- | --- |
| `btop.desktop` | Contenu de terminal |
| `jshell-java-openjdk.desktop` | Contenu de terminal |
| `jshell-java17-openjdk.desktop` | Contenu de terminal |
| `julia.desktop` | Contenu de terminal |
| `nvim.desktop` | Contenu de terminal |
| `yazi.desktop` | Contenu de terminal |
| `org.kde.akonadi.desktop` | Aucun Exec disponible ni activation DBus |
| `org.quickshell.desktop` | Aucun Exec disponible ni activation DBus |

Les cinq surfaces présentes au moment de cette lecture étaient classées
(Proton Pass, Kitty, ChatGPT, WhatsApp et LiMusic). Firefox et les deux terminaux
supplémentaires présents au début de l'incident n'étaient plus dans l'arbre ;
aucune application n'a été ouverte ou fermée pour cet inventaire. Le checkpoint
canonique et les trois fichiers de récupération ont conservé leurs SHA-256.

## Vérifications

`tests/session_v2/test_installed_catalog.py` couvre les correspondances exactes,
les collisions et priorités, les politiques réservées, les entrées non affichées,
la résolution XDG utilisateur/système/Flatpak dans un processus isolé, les
overrides Hidden, la lecture non bloquante des fichiers non réguliers, la
revalidation du lanceur, l'absence d'arguments issus du snapshot, la sauvegarde
multi-fenêtre et le report avant mutation lorsqu'une fenêtre manque.

Les fixtures sont des fichiers temporaires et des arbres IPC inertes. Les
lancements sont interceptés. Aucun test n'ouvre les applications de l'utilisateur.
Le catalogue explicitement injecté par les tests est hermétique et ne découvre
pas les applications de la machine.

## Correctif ciblé Immich — 11 novembre 2026

Après la correction des parents `tabbed`/`stacked` unaires, la déconnexion a
renvoyé `APPLICATION_UNSUPPORTED`. L'inventaire Sway et GIO a identifié la
webapp Immich `firefox.webapp-40f22022-70af-4784-81ee-100e6a56dc50`,
présente dans le lanceur utilisateur et démarrée par l'autostart Sway sur
le workspace 8. Le catalogue excluait cette webapp avec `provider-required`.

La politique explicite `immich-web` adopte `managed-autostart` et
`managed_by=sway-autostart`, comme WhatsApp. Le host natif Firefox reconnaît
uniquement les webapps explicites gérées par Sway, jamais tout le préfixe
`firefox.webapp-*` ; il ne leur attribue pas d'UUID de fenêtre navigateur.
Les webapps inconnues restent refusées.

Validation : 153 tests Python PASS, reconstruction SwayFX/XWayland privé avec
ChatGPT, WhatsApp et Immich PASS ; les agencements unaires `tabbed` et `stacked`
restent PASS. Le host Firefox a été reconnecté sans fermer le navigateur.
Une capture réelle sur le bureau utilisateur (`capture --execute`, sans
sauvegarde ni déconnexion) a réussi : six applications, sept fenêtres ;
le checkpoint automatique antérieur est inchangé. La déconnexion et la
restauration physiques restent à valider par l'utilisateur.

## Références

- [Desktop Entry Specification — recognized keys](https://specifications.freedesktop.org/desktop-entry/latest/recognized-keys.html)
- [GioUnix.DesktopAppInfo](https://docs.gtk.org/gio-unix/class.DesktopAppInfo.html)
- [Gio.AppInfo.launch](https://docs.gtk.org/gio/method.AppInfo.launch.html)
