# Choix de session Labfy — préparation V1

La V2 complète cette préparation : [connexion et récupération](LOGIN_RECOVERY_V2.md).
Les valeurs de préférence et chemins de bundle ci-dessous sont les observations
historiques V1 ; utiliser le nouveau bundle V2 pour toute future installation.

## Contrat et état

Le greeter transmet à **greetd après authentification PAM**, avec exactement
`env=[]`, l'un des deux argv suivants. Il ne lance pas UWSM lui-même.

| Interface | Identifiant interne | argv exact |
| --- | --- | --- |
| SwayFX — Stable | `stable` | `["/usr/bin/uwsm", "start", "sway.desktop"]` |
| SwayFX Mosaic — Expérimental | `mosaic` | `["/usr/bin/uwsm", "start", "swayfx-mosaic-test.desktop"]` |

`session_command()` et `Client.start()` sans argument donnent Stable. Toute
valeur fournie doit être une chaîne de type exact `str`, égale à `stable` ou
`mosaic`. `None`, booléens, listes, chemins, identifiants desktop et arguments
supplémentaires sont refusés. La table est un `MappingProxyType` de tuples.
`AuthFlow.begin(username, selection="stable")` capture le choix avant la
première requête PAM ; `AuthFlow.start()` ne reçoit plus de sélection et utilise
cet instantané. Une authentification ne permet qu'une tentative de lancement.

Le choix est visible avant validation du mot de passe. Compte, session, saisie
manuelle et envoi sont bloqués pendant chaque requête. Entre deux invites, un
changement de compte/session annule l'ancienne conversation avant d'en commencer
une autre ; le nom manuel est revérifié avant d'envoyer une réponse. Les erreurs
PAM et de socket invalident l'état. Un refus de lancement ne sélectionne jamais
automatiquement une autre session. Le prochain démarrage du greeter revient à
Stable ; aucune préférence de session n'est sauvegardée.

Le code est **implémenté et validé localement**, sans activation système.
L'approbation visuelle humaine et la connexion sur le siège physique restent
**NOT_RUN** pour cette version. Ce composant d'accueil ne qualifie pas Mosaic
comme daily-driver. Le greeter ne scanne aucun HOME et ne lit/écrit jamais
`uwsm/default-id`. Les entries utilisateur sont résolues par UWSM dans le compte
authentifié, pas par le compte `greeter`.

## Prérequis constatés le 15 octobre 2026

- Stable : `/usr/share/wayland-sessions/sway.desktop`, root:root, `0644`.
- Mosaic : `~/.local/share/wayland-sessions/swayfx-mosaic-test.desktop`, accessible
  au compte utilisateur (`0600`), avec son launcher personnel (`0700`). Les
  autres comptes peuvent voir le choix fixe puis subir un refus UWSM si cette
  entrée leur manque. Il n'y a ni scan des HOME ni repli silencieux.
- Binaire expérimental contrôlé par le launcher : SHA-256
  `91f48aae2675331e0a2c60ec2fedf983745c521c75232c704a6516a4140801fb`.
  Aucun build, lancement physique ou changement du launcher dans ce ticket.
- UWSM est installé. Son aide locale confirme `start -n` comme dry-run ; cette
  commande n'est pas nécessaire à la validation et n'a pas été exécutée.
- `getty@tty2.service` est actif lors du contrôle en lecture seule.
- Écart à l'hypothèse du ticket : `default-id` contient déjà
  `swayfx-mosaic-test.desktop`. Il est préservé byte-for-byte, SHA-256
  `480df66fb40037fadd7801ffe1850c65ca65baed9829b38500993639b4faf7f3`.
  Le choix Stable explicite du nouveau greeter fonctionne indépendamment de ce
  fichier ; l'ancien greeter installé utilise encore `start default`.

## Aperçu contrôlé

Depuis la racine des dotfiles, sans droits root :

```sh
GDK_BACKEND=wayland python3 -B greetd/src/labfy_greeter.py --preview
```

L'aperçu charge le **CSS source**, même quand l'ancienne version est installée.
Stable est présélectionné. Le choix Mosaic est manipulable à la souris et au
clavier ; le mnémonique du libellé Session est Alt+S. Authentification, workers
PAM, alimentation et écriture de luminosité sont inactifs. Fermer la fenêtre
termine l'aperçu ; aucune commande IPC Sway n'est nécessaire.

Les captures natives GTK `preview-stable.png` et `preview-mosaic.png`, dans le
LAB privé `/var/tmp/labfy-greeter-dual-session-mkzppvge/`, proviennent de la
fenêtre réellement affichée dans Sway via `Gtk.WidgetPaintable` et son renderer.
Elles ne capturent pas les autres fenêtres du bureau. La taille échantillonnée
est 1131 × 853 ; le libellé Expérimental est entièrement visible. Cela ne prouve
pas une recette fullscreen sur VT1 ni toutes les tailles de sortie.

## Mise à jour ciblée — après un accord distinct seulement

**Ne pas utiliser `scripts/install.sh --prepare` pour cette mise à jour** : cette
commande écrit déjà les sources installées et prépare d'autres éléments système.
Le nouvel outil n'appelle ni installateur historique, ni systemctl, ni sudo,
ni shell. Les commandes root ci-dessous sont une procédure préparée, non exécutée.

`session-update.py prepare BUNDLE` est une préparation utilisateur : elle lit
les quatre originaux installés root:root `0644`, vérifie leurs SHA attendus et
écrit uniquement un nouveau bundle privé. `check BUNDLE` est en lecture seule.
Le bundle contient les copies `.old`, `.new`, le manifeste et une copie de
l'outil, sans dépendance au dépôt pour le rollback.

```sh
# Déjà effectué sans root pour ce ticket ; le répertoire doit être neuf.
python3 -B greetd/scripts/session-update.py prepare /var/tmp/mon-lab-prive/bundle
python3 -B greetd/scripts/session-update.py check /var/tmp/mon-lab-prive/bundle
```

Le bundle préparé pour la revue est
`/var/tmp/labfy-greeter-dual-session-mkzppvge/bundle` (LAB `0700`, fichiers du
bundle `0600`). Conserver le LAB jusqu'à validation ou abandon explicite, sans
le traiter comme sauvegarde durable : `/var/tmp` peut être nettoyé. Avant une
installation approuvée, vérifier les hashes du manifeste et de l'outil examinés,
puis copier ce bundle dans un répertoire root privé **neuf** :

```sh
# UNIQUEMENT APRÈS APPROBATION EXPLICITE — NON EXÉCUTÉ
sudo install -d -o root -g root -m 0700 /var/lib/labfy-greeter/session-selector-v1
sudo install -o root -g root -m 0600 \
  /var/tmp/labfy-greeter-dual-session-mkzppvge/bundle/* \
  /var/lib/labfy-greeter/session-selector-v1/
sudo python3 -B /var/lib/labfy-greeter/session-selector-v1/session-update.py \
  check /var/lib/labfy-greeter/session-selector-v1
sudo python3 -B /var/lib/labfy-greeter/session-selector-v1/session-update.py \
  apply /var/lib/labfy-greeter/session-selector-v1
```

Ne pas recopier le bundle par-dessus un bundle déjà utilisé : préserver son
journal et ses originaux. Conserver cette copie root jusqu'à acceptation de la
recette et décision explicite de supprimer la sauvegarde. Les quatre seules
cibles sont `greetd_ipc.py`, `auth.py`, `labfy_greeter.py` sous
`/usr/local/libexec/labfy-greeter/`, et le CSS sous
`/usr/local/share/labfy-greeter/`. Aucun changement de `config.toml`, PAM,
run-ui, start-compositor, service UWSM ou binaire Sway.

Préflight global des types, propriétaires, modes et SHA avant remplacement.
Parents sans lien symbolique et non modifiables par un autre compte. Verrou
root global `/var/lib/labfy-greeter/session-selector-update.lock` (`0600`) pour
sérialiser les bundles. Fichiers et répertoires sont synchronisés par `fsync` ;
chaque publication se fait par `rename` sur le même système de fichiers.
L'ensemble des quatre fichiers n'est pas une transaction atomique du système
de fichiers : ne pas ouvrir une nouvelle connexion pendant leur mise à jour.
Une erreur ordinaire restaure les originaux. Un arrêt brutal laisse un journal
`applying` ; `rollback` ou le prochain `apply` restaure les originaux. Ce dernier
s'arrête ensuite avec une erreur explicite demandant vérification et nouvel
essai. Les opérations répétées sont idempotentes. Un contenu extérieur divergent
n'est pas écrasé. Une panne au milieu de l'écriture d'un temporaire peut laisser
un fichier caché `.labfy-session-*` dans le répertoire cible ; il n'est jamais
chargé comme module et son éventuelle suppression nécessite inspection root.
Aucun succès du script ne déclenche redémarrage, logout ou changement de TTY.

## Première connexion et retour à Stable

Après installation approuvée, terminer la session par le chemin habituel quand
l'utilisateur est prêt. Sur Labfy :

1. Vérifier le compte et le contrôle **Session**. Stable est présélectionné.
2. Choisir **SwayFX — Stable** pour la session habituelle, ou explicitement
   **SwayFX Mosaic — Expérimental** pour l'essai non qualifié.
3. Saisir le mot de passe et répondre aux éventuelles invites PAM suivantes.
4. Pour revenir à Stable après Mosaic, terminer l'essai puis conserver Stable
   sur le prochain écran Labfy. Aucune commande `uwsm select` n'est requise.

Si l'entrée Mosaic ou son binaire temporaire a disparu, UWSM/le launcher peut
refuser le lancement. Un refus immédiat de `start_session` reste affiché dans
le greeter. Un échec ultérieur d'UWSM survient après son acceptation par greetd
et ne peut pas être présenté par un GTK déjà fermé : le secours greetd/TTY reste
nécessaire. Aucun échec ne bascule silencieusement vers une autre session.

En cas de problème, **Ctrl+Alt+F2**, connexion console, puis restauration ciblée :

```sh
# Après installation approuvée seulement ; ne lance ni Mosaic ni Sway.
sudo python3 -B /var/lib/labfy-greeter/session-selector-v1/session-update.py \
  rollback /var/lib/labfy-greeter/session-selector-v1
```

Cela rétablit l'ancien Labfy, avec son ancien comportement `start default`.
Compte tenu du `default-id` observé, **ce rollback n'implique pas une sélection
Stable**. Il est indépendant du launcher Mosaic et ne réécrit aucune préférence.
Une relance de greetd depuis TTY2 nécessiterait une instruction distincte ;
aucun redémarrage automatique n'est prévu. L'ancien rollback système vers
Tuigreet reste documenté dans le README historique, sans avoir été exécuté ici.
