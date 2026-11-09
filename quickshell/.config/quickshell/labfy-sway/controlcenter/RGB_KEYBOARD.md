# Clavier RGB — LABFY_RGB_V3

La sous-page interne `RGB_KEYBOARD` est ajoutée en fin du StackLayout (index 17),
sans déplacer les indices historiques. Elle s'ouvre depuis Réglages rapides →
Clavier RGB et utilise la navigation retour habituelle. Aucune nouvelle fenêtre.

Le singleton `rgbkeyboard/RgbKeyboardService.qml` possède un seul Process pour
l'ensemble des barres/écrans. Il invoque directement
`~/.local/bin/labfy-rgb` avec un tableau d'arguments, sans shell, sudo ou pkexec.
Ce chemin est actuellement un lien vers `/home/fy59/labfy-rgb/build/labfy-rgb`.

Le CLI utilise le périphérique I2C/ASUS/5570 découvert, vérifie son descripteur
et obtient un verrou exclusif. La règle uaccess dédiée fournit l'accès de la
session locale active ; QuickShell et le CLI restent des processus utilisateur.

## Affichage et commandes

`status --json` schéma 1 distingue disponibilité, observed_mode (actuellement
unknown) et commanded_mode/last_color/last_percent issus de l'historique local.
L'interface dit « Dernière commande » et ne présente pas ces données comme une
mesure de l'éclairage réel. En mode ASUS, la couleur physique reste inconnue.

Les huit pastilles utilisent une palette saturée pour le clavier uniquement :
Violet #8000FF (premier choix), Bleu #0040FF, Cyan #00FFFF, Vert #00FF40,
Rose #FF0080, Rouge #FF0000, Orange #FF6000, Jaune #FFFF00.
Le thème général Catppuccin Mocha et son accent restent inchangés.

Cliquer une pastille applique immédiatement `set #RRGGBB`, sans shell ni sudo,
avec l'intensité par défaut du CLI (100 %). Le brouillon est initialisé à Violet,
sans application automatique à l'ouverture. Saisir une couleur personnalisée ou
déplacer le slider ne lance aucun Process : utiliser Appliquer ou Intensité.

- Appliquer : `set #RRGGBB P`, couleur et intensité réunies en une transaction.
- Intensité : `brightness P`, exige une dernière couleur connue du CLI.
- Éteindre : `off`, intensité/RGB à zéro sous contrôle logiciel.
- Mode ASUS : `auto`, disponible même si le dernier status échoue.
- Actualiser : lecture `status --json` ; pas de polling permanent.

Un Process déjà réservé refuse toute autre commande. Les boutons sont désactivés
pendant son exécution. Après commande, une seule actualisation de statut suit.
Code non nul, démarrage impossible et sortie JSON invalide sont traités ; une
commande réussie ne promet pas un état visuel permanent. Les diagnostics sont
bornés dans l'interface. IPC `rgbKeyboard state` est strictement en lecture seule.

L'intensité HID est distincte de `asus::kbd_backlight` WMI. Les essais V3 n'ont
pas changé WMI. Leur interaction hors de ces essais n'est pas caractérisée :
ne pas synchroniser automatiquement les deux curseurs.

## Restauration au démarrage — opt-in

« Restaurer ma couleur au démarrage » est **désactivé par défaut**, laissé ainsi
pendant la validation réelle. Activer la case constitue le choix utilisateur.
La préférence et la dernière configuration acquittée depuis cette interface sont
conservées par QtCore.Settings dans `$XDG_CONFIG_HOME/labfy-rgb/quickshell.ini`
(ou `~/.config/labfy-rgb/quickshell.ini`). Pas de secret dans ce fichier.

À un prochain chargement de QuickShell, un seul contrôle différé est effectué.
Une restauration ne part que si l'option est active, le périphérique accessible,
le RGB et pourcentage valides, et la dernière préférence de mode logicielle.
Une consigne firmware connue du CLI ou demandée via Mode ASUS l'emporte.
Une opération échouée invalide la préférence de mode pour éviter un rejeu incertain.
Aucune boucle de retry, service root ou service/autostart systemd ajouté.
Aucune restauration automatique après veille n'est activée dans cette version.

Le cache runtime C est indépendant des préférences :
`$XDG_RUNTIME_DIR/labfy-rgb/state.bin`, répertoire 0700/fichier 0600,
format versionné 003, publié atomiquement. L'ancien cache V2 root n'est ni lu
ni migré. Le cache runtime n'est pas une autorité de capacités HID.

## Validation

`python3 tests/test_quickshell_rgb_keyboard.py` exécute le service QML de production
sur un exécutable fictif, avec répertoires de configuration/runtime temporaires.
Aucune écriture matérielle : arguments des huit préréglages, sérialisation, refresh,
erreur code 4, exécutable disparu et absence d'activation par défaut sont vérifiés.

`qmllint` porte sur les trois QML modifiés/ajoutés. Les journaux de la session
active et les observations visuelles sont conservés dans le projet CLI,
`/home/fy59/labfy-rgb/audit/v3/`. Le contrôle final du rendu et des préférences
reste accessible sans redémarrer SwayFX.
