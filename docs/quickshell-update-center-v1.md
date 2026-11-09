# Labfy Update Center V1

Le clic sur l’indicateur de mises à jour de la barre ouvre le centre intégré à
QuickShell. L’indicateur reste accessible à zéro pour donner accès à la maintenance
et aux annonces. Le thème utilise les rôles Catppuccin existants, Lavender pour les
titres et des rayons de 4 px.

## Architecture initiale et évolution

`status/UpdatesIndicator.qml` lisait uniquement les compteurs Arch/AUR d’un JSON
atomique dans `$XDG_RUNTIME_DIR/labfy-quickshell-updates.json`, sans action au clic.
Le service utilisateur `labfy-quickshell-updates.service` exécutait
`bin/check-updates.py` ; son timer existant vérifiait toutes les dix minutes.
Les commandes étaient `checkupdates` et `yay -Qua`.

Ce service et ce timer restent les seuls propriétaires de la vérification
périodique. Le collecteur conserve maintenant les paquets, versions installées et
candidates, origine Arch/AUR, repères informatifs et état de chaque tentative.
La vérification manuelle demande le démarrage du même service. `checkupdates`
utilise sa base temporaire ; aucune synchronisation isolée de la base système,
installation ou élévation n’est effectuée pendant la collecte.

`status/UpdateCenter.qml` est un PopupWindow ancré à la barre.
`RightStatusArea.qml` et `Bar.qml` assurent l’exclusion avec les autres panneaux et
la fermeture lors d’une authentification. Le grab existant ferme le centre sur
clic extérieur ; Échap et le bouton × permettent également de fermer.
Le ciblage IPC par sortie est `updatesUi-<sortie>` : `open`, `close`, `isOpen`.
Aucune action d’installation n’est exposée par IPC.

## Données, erreurs et performances

Les listes officielles et AUR restent séparées. La recherche et les filtres sont
locaux. La liste virtualisée accepte les listes longues. Les repères noyau,
système, graphique et session ne prédisent jamais une panne ; les noyaux
personnalisés publiant un `pkgbase` dans `/usr/lib/modules` sont aussi reconnus.

Le fichier est publié par remplacement atomique. Un `flock` partagé protège les
vérifications et l’installation Labfy, y compris depuis plusieurs sorties. Ce
verrou ne prétend pas contrôler les outils externes : pacman garde son propre
verrou système. Les admissions QML sont synchrones pour rejeter un double clic.
Chaque commande de vérification dispose de 120 s, dans le service existant limité
à 270 s. Un état de progression abandonné devient réessayable après ce délai.
En cas d’échec d’une source, ses anciens résultats sont conservés avec l’erreur ;
ils ne deviennent pas un faux zéro. Une connexion HTTPS est sondée seulement après
une erreur du collecteur pour distinguer une connexion indisponible.

Le renderer observe le cache. Son ancien timer de récupération est réutilisé
uniquement avant le premier chargement ou pendant l’ouverture du popup ; aucun
nouveau timer ni démon n’est ajouté. Les processus de maintenance et d’actualités
sont ponctuels et asynchrones, lancés à l’ouverture.

## Installation interactive et aperçu

« Mettre à jour le système » demande une confirmation dans QuickShell, puis ouvre
Kitty avec `bin/update-terminal.py`. L’app_id dédié `labfy-update-center` cible
une règle dans `sway/.config/sway/rules` : fenêtre flottante, centrée, 65 % de la
largeur et 60 % de la hauteur de la sortie active. Installation et aperçu partagent
ce placement ; les autres fenêtres Kitty conservent leur comportement. Le terminal présente l’opération et exige la
saisie exacte de `METTRE A JOUR`. L’opération complète est `yay -Syu --confirm`,
avec les options de yay 13 suivantes :

- `--sudoloop=false` : aucune boucle de maintien de sudo ;
- `--cleanafter=false` : pas de nettoyage automatique des sources par Labfy ;
- `--useask=false` : pas d’acceptation automatique des conflits ;
- `--askremovemake` : question avant suppression des dépendances de compilation ;
- `--noanswerclean --noanswerdiff --noansweredit --noanswerupgrade` : pas de réponses
  préenregistrées aux menus.

Les options sont limitées à cette invocation et ne sont pas sauvegardées. Le
terminal affiche le code de sortie, demande au service existant de revérifier,
puis attend Entrée. Après une erreur, il rappelle de terminer la mise à jour
complète avant toute autre installation. Les décisions interactives de yay et la
lecture des PKGBUILD restent à la charge de l’utilisateur.

« Aperçu Kitty » utilise `--dry-run` : aucune commande de paquets ni actualisation
n’est exécutée. Les tests de la branche affirmative interceptent tous les appels
au gestionnaire de paquets. Aucune installation réelle ne fait partie des tests.

## Maintenance en lecture seule

L’onglet affiche les 35 dernières lignes de transactions ALPM présentes dans une
queue de lecture de 256 Kio de `/var/log/pacman.log`, les fichiers `.pacnew` et
`.pacsave` accessibles sous `/etc`, et les services système/utilisateur en échec.
La recherche ne suit pas les symlinks de répertoire et est limitée à 4 s / 50 000
entrées de répertoire ; toute limite ou permission insuffisante est signalée.
Ce périmètre ne garantit pas la découverte de fichiers situés hors `/etc`.
Aucun fichier de configuration n’est fusionné, supprimé ou modifié.

`/run/reboot-required`, s’il existe, est présenté comme une demande détectée.
L’absence des modules du noyau actif est une recommandation, pas une preuve
universelle d’obligation de redémarrer. L’absence de signal ne garantit pas qu’un
redémarrage est inutile. Les journaux du système et du collecteur sont accessibles
dans Kitty. Aucun nettoyage de cache n’est exécuté.

## Annonces officielles

Source : <https://archlinux.org/feeds/news/>. Cache utilisateur
`$XDG_CACHE_HOME/labfy-update-news.json` (sinon `~/.cache`), renouvelé après 6 h
lors d’une ouverture. Après échec, un délai de 10 min évite les tentatives
répétées ; les annonces en cache restent visibles. La lecture réseau est limitée
à 1 Mio et 12 s. Les titres sont rendus comme texte brut. Seuls les liens HTTPS
vers `archlinux.org` sont ouvrables.

Le badge d’intervention manuelle est posé uniquement lorsque le titre officiel
l’annonce explicitement en anglais. L’absence de badge ne dispense pas de lire
l’annonce ; le contenu n’est pas analysé pour deviner une applicabilité. Aucune
correspondance avec les paquets installés et aucune exécution de texte distant.

## Validation non destructive

- `python3 -m unittest discover -s tests -p 'test_quickshell*.py' -v` : 16 tests,
  dont 13 du collecteur/terminal, un scénario QML et deux de régression Hyprwhspr.
- Le scénario QML charge les composants de production avec commandes interceptées
  dans une copie temporaire : zéro, 600 paquets Arch/AUR, recherche/filtres,
  navigation, données de maintenance/annonces, actualisation et double appel,
  récupération d’une vérification expirée, fermeture/réouverture et argv d’aperçu.
  Il nécessite QuickShell et une session Wayland ; son popup synthétique désactive
  le grab faute de série d’entrée utilisateur. Le popup de la vraie barre garde
  son grab.
- Tests JavaScript existants : StatusColorRoles, PercentMath,
  PercentPresentation, ScrollSteps, OSD observation.
- `qmllint` sur les cinq QML modifiés/ajoutés et `git diff --check`.
- Lecture réelle du service, des transactions, fichiers `/etc`, services en échec
  et flux officiel ; ouverture du vrai Kitty avec `--dry-run` seulement.

Dépendances : Python standard, QuickShell/QtQuick.Controls, systemd utilisateur,
pacman-contrib (`checkupdates`), yay et Kitty, tous déjà installés. Aucune nouvelle
dépendance. Les réglages pacman et systemd sont préservés. La seule règle SwayFX ajoutée cible
l’app_id du terminal de mise à jour, à la demande de l’utilisateur.

## Résultat de validation en session

Validation finale : 16 tests Python passants en 18,921 s ; les cinq suites
JavaScript citées passent. `qmllint`, compilation Python et `git diff --check`
sont passants. `sway -C` retourne 0 (avertissements EGL de détection GPU), puis
le rechargement des règles Sway retourne `success: true`, sans redémarrage de
session. Un vrai Kitty lancé avec `--dry-run` et l’app_id de production est
confirmé dans `floating_nodes` de l’arbre Sway : rectangle 1482 × 830, position
401,319 sur la sortie actuelle. Seule cette fenêtre d’aperçu est ensuite fermée.

Lecture locale : 10 fichiers `.pacnew`/`.pacsave`, 35 lignes ALPM, aucun service
en échec signalé ; des permissions insuffisantes sous `/etc` sont remontées dans
l’interface. La recherche reste donc explicitement partielle. Le flux officiel
est téléchargé et ses annonces sont mises en cache. QuickShell reste actif avec
le PID 378053 et `NRestarts=0` ; aucun redémarrage du service n’a été demandé.
L’installation réelle, la résolution de conflits AUR et un redémarrage système
ne sont volontairement pas exécutés. Le contrôle visuel et ergonomique final
reste à effectuer par l’utilisateur dans les trois onglets.
