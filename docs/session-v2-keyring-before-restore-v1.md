# Session V2 — trousseau avant restauration (22 octobre 2026)

État : implémentation et validation isolées ; **non déployé**, vrai login non
validé. Base `d16aa69f`, branche `fix/session-v2-keyring-before-restore-20261022`.
Le dépôt principal était propre ; aucun autre worktree n'a été modifié.

## Diagnostic et preuves disponibles

À 08:01:35 CEST, systemd démarre GNOME Keyring ; QuickShell démarre à
08:01:38. À 08:01:48 le prompter reçoit BeginPrompting, crée GcrPromptDialog,
puis commence un password prompt. L'incident fourni situe le démarrage du
prompt à 08:01:48.235 et le rapport d'échec à 08:01:48.482. Le focus attendu
Firefox/con_id 10 est remplacé par con_id 18 après les six frontières du guard.
Ces événements concordent avec une activation du trousseau pendant la fenêtre
de validation finale. **L'identité historique de con_id 18 et la causalité ne
sont pas démontrées.** Aucune capture d'arbre contemporaine avec PID/starttime
ne permet ici de les établir. Même limite pour l'occurrence de 06:11:59.

Les abonnements IPC Sway indiquent la fenêtre devenue active, pas l'origine
(user input ou commande d'un autre client IPC) d'un changement de focus. Un
app_id seul n'est pas une preuve de causalité. Une future investigation peut
corréler les événements fenêtre/workspace horodatés, con_id, PID/starttime et
les événements du prompter ; elle doit laisser « non attribué » ce qui le reste.
Ne pas activer de trace d'échange secret pour ce diagnostic.

## Audit de l'installation réelle (lecture seule)

- `/etc/pam.d/greetd` : securetty, nologin, puis inclusions auth/account/session
  de system-local-login. Aucune règle gnome-keyring. SHA-256 observé :
  `993a3096c2b113e6800f2abbd5d4233ebf1a97eef423990d3187d665d3490b92`.
- Inclusions : system-local-login → system-login → system-auth. pam_unix utilise
  try_first_pass ; pam_systemd est dans la chaîne session avant le retour à
  greetd. Les sauts numériques de system-auth ne sautent pas une règle ajoutée
  après l'inclusion dans greetd. Rien de cette pile n'est modifié.
- Le greeter installé dans `/usr/local/libexec/labfy-greeter` répond aux messages
  PAM avec post_auth_message_response, sur la même conversation greetd. Il ne
  réauthentifie pas le mot de passe localement. Le code installé est antérieur
  au sélecteur de session du dépôt mais possède ce même transport des réponses.
- Module présent : `/usr/lib/security/pam_gnome_keyring.so`, paquet
  gnome-keyring `1:51.1-1`, greetd `0.10.3-2`, python-gobject `3.58.1-1`.
- Secret Service appartient à gnome-keyring-daemon. Un processus observé :
  `gnome-keyring-daemon --foreground --components=pkcs11,secrets,ssh`.
  ReadAlias(default) renvoie `/org/freedesktop/secrets/collection/Default_5fkeyring` ;
  ReadAlias(login) renvoie `/`. Locked est false lors de la relecture finale
  (cet état courant ne prouve pas son état pendant l’incident). Aucun contenu des fichiers du trousseau n'a été lu.
  Les noms présents sont Default_keyring.keyring, default et user.keystore.
- L'unité utilisateur masque celle du paquet. Elle omet Requires=socket et le
  `--control-directory=%t/keyring` explicite de l'unité distribuée. Son lien
  d'activation est dans default.target.wants, même si Install mentionne
  graphical-session.target. Le socket `%t/keyring/control` est actif.
- D-Bus possède aussi une entrée d'activation `--start --foreground
  --components=secrets`. Les fichiers XDG autostart du paquet utilisent --start
  et OnlyShowIn=GNOME;Unity;MATE;Cinnamon. Ils ne démontrent donc pas un second
  lancement sous Sway. Aucun autre lancement n'a été trouvé dans les sources
  Sway/QuickShell/greetd ; **une seule instance observée ne prouve pas l'absence
  de toute course de démarrage**.

### Décision PAM : pas de patch applicable dans cette mission

L'intégration habituelle place auth optional pam_gnome_keyring.so après
l'authentification principale et session optional pam_gnome_keyring.so
auto_start après l'inclusion de session (donc après pam_systemd). Le transport
du greeter et PAM_AUTHTOK sont structurellement compatibles avec ce schéma.
Cela n'établit pas que Default_keyring soit le trousseau login, ni que son mot
de passe soit identique à celui du compte. Ces faits ne sont pas testés avec
un mot de passe dans cette mission.

Le module GNOME cible le trousseau **login**, identifié en interne par CKA_ID.
Son chemin de déverrouillage peut le créer s'il manque. L'alias login est absent,
aucun fichier login n'est listé, et le rôle interne de Default_keyring n'est pas
prouvé. Activer auto_start pourrait donc provoquer une création et ne démontre
pas le déverrouillage du default existant. Ce mécanisme est vérifié dans le
[code GNOME Keyring 51.1, unlock_or_create_login](https://raw.githubusercontent.com/GNOME/gnome-keyring/51.1/daemon/login/gkd-login.c).
La [documentation PAM GNOME](https://wiki.gnome.org/Projects/GnomeKeyring/Pam)
décrit également la cible login et les règles usuelles. **Aucun fichier PAM candidat à installer
n'est livré**, aucun essai PAM réel n'est effectué. Une validation statique de
la syntaxe de deux règles ne validerait pas ces conditions opérationnelles.

Le contrôle optional protège normalement la décision d'authentification
principale contre un échec du module ; il ne garantit pas à lui seul l'absence
d'attente ni d'effets de bord. Ne pas prendre cette analyse pour une preuve
qu'un changement PAM quelconque est sans risque.

Une future tranche PAM exige une autorisation distincte, la confirmation
humaine du trousseau cible sans enregistrer le mot de passe, et une étude de
l'unité/socket du paquet comme propriétaire unique du démon. Si un patch
compatible est alors établi, l'application privilégiée doit sauvegarder le
fichier root:root/0644, contrôler le hash de départ, installer atomiquement la
copie validée et conserver un accès de secours hors greeter. Le rollback doit
réinstaller exactement la sauvegarde, sans modifier les inclusions système.
Aucune de ces opérations ni aucun logout/reboot n'a été exécuté ici.

Aucune modification de l'unité utilisateur n'est nécessaire à la barrière
D-Bus. La normalisation de cette unité avec une future intégration PAM doit
être validée au login ; elle n'est pas appliquée sur le bureau actif.

## Contrat de la barrière

`session_v2/keyring.py` utilise PyGObject/Gio et une connexion D-Bus privée :

1. Résoudre/activer Secret Service avec une attente bornée, puis fixer son
   propriétaire D-Bus unique pour toutes les opérations.
2. ReadAlias(default) doit correspondre à la collection auditée ci-dessus.
   Default absent/différent est un refus explicite. Si login existe, il doit
   désigner la même collection. Login absent autorise le parcours manuel ; il
   ne vaut jamais preuve de compatibilité PAM. Une installation utilisant une
   autre collection doit faire réauditer cette constante avant intégration.
3. Lire org.freedesktop.Secret.Collection.Locked par Properties.Get. READY
   exige un vrai booléen false, avec propriétaire inchangé.
4. Un clic Déverrouiller appelle Service.Unlock. S'il retourne un Prompt,
   s'abonner à Completed **avant** Prompt(""). Le window-id vide présente un
   prompt non parenté, sans prétendre à un handle X11/Wayland inexistant.
5. Garder la connexion vivante, attendre Completed non annulé, puis relire
   alias/propriétaire/Locked. Une fin de prompt avec Locked=true refuse READY.
6. Limites : connexion/auth D-Bus 2 s, appels individuels au plus 2 s, budget
   de lecture 8 s, opération interactive 90 s, nettoyage Dismiss au plus 1 s,
   puis relecture avec budget 8 s. Un timeout n'autorise rien. Un mot de passe
   incorrect peut maintenir le prompt GNOME ouvert jusqu'à correction,
   annulation ou timeout ; le client n'essaie jamais de deviner cette cause.
7. Dismiss/fermeture de la connexion ne concernent que le prompt possédé. Le
   traitement SIGTERM réveille la boucle GLib et permet ce nettoyage. Un arrêt
   brutal du processus ferme sa connexion ; il ne laisse aucune autorisation
   persistante. Aucun fichier READY/token n'est produit.

Les commandes `keyring-status` et `keyring-unlock --execute` retournent
uniquement un état KEYRING_* et un code de diagnostic fixe. Aucun OpenSession,
GetSecret(s), SearchItems, changement de mot de passe, création de collection
ou lecture de fichier de trousseau n'est utilisé. Les erreurs D-Bus libres et
le payload de résultat de Completed ne sont pas journalisés.

### Concurrence et transactions

Le verrou privé `session-v2/keyring.lock` sérialise les helpers entre processus.
Une seconde demande voit KEYRING_UNLOCKING/KEYRING_OR_RESTORE_BUSY et ne crée
pas un second prompt. Avant Unlock, le helper vérifie aussi le verrou de
transaction existant (y compris celui hérité par un guard survivant).

Les CLI `apply-last` **et** `apply` prennent keyring.lock, relisent D-Bus sans
ouvrir de prompt, puis appellent l'Executor inchangé en gardant le verrou
jusqu'à son retour. Ordre : keyring.lock puis transaction.lock. Aucune voie
CLI de restauration n'est autorisée par le seul booléen du QML. Un refus de
barrière ne publie aucun Attempt/Recovery et ne nettoie aucun ancien journal.
Les appels internes directs à Executor restent une API de moteur ; ils ne
constituent pas une commande utilisateur de restauration.

La décision « Nouvelle session » conserve uniquement le verrou de transaction
historique. Elle reste donc disponible pendant une attente du trousseau.
QuickShell arrête son helper lors de ce choix. Un autre helper déjà en cours
n'est pas tué par une instance qui ne le possède pas.

### QuickShell

Le singleton démarre sa lecture indépendamment du checkpoint. Le chooser
reconstruit aussi l'état backend au redémarrage ; un déverrouillage détenu par
une autre instance est observé par polling borné des commandes, jamais relancé.
Les erreurs et annulations proposent une nouvelle action explicite. Le panneau
retire sa capture clavier avant le prompt natif ; il conserve le bouton
Nouvelle session. Après READY, seul un clic Restaurer appelle le chemin
historique de retrait de surface, prewarm, Guard et validation finale.

Le gestionnaire de sessions nommées reçoit également le refus du backend et
l'affiche sans charger un ancien rapport d'échec. Les commandes de diagnostic,
checkpoint, sauvegarde, nouvelle session et ouverture normale du bureau ne
dépendent pas d'un trousseau disponible.

## Limite tardive et invariants conservés

Secret Service peut reverrouiller une collection à tout instant. Le verrou de
la barrière ne contrôle pas les autres applications, un autre trousseau ou
un autre client Secret Service. Il ne garantit donc pas qu'aucun prompt ne
pourra jamais apparaître après l'admission. Un prompt déjà demandé par un
client externe n'est pas notre objet Prompt et ne peut être annulé arbitrairement.
La [spécification Secret Service](https://specifications.freedesktop.org/secret-service/latest/unlocking.html) précise cette course inhérente.

L'initialisation du default nécessaire à notre parcours est traitée avant la
restauration. Si une activation tardive interfère néanmoins, les mêmes preuves
con_id/PID/starttime/workspace/output et les mêmes postconditions de focus
refusent la transaction. **Aucun focus observé n'est remplacé pour fabriquer
un succès.** L'expérience headless crée une surface synthétique après
`after-guard-finish` et exige RECOVERY_FOCUS_MISMATCH, final_focus_verified=false
et RECOVERY_REQUIRED. Elle ne prétend pas identifier le dialogue de 08:01:48.

Checkpoint V1, scratchpad V2, Guard.prepare, journaux et schémas Recovery,
placement et validations de focus ne sont pas modifiés. Les tests qui isolent
le prewarm simulent explicitement la nouvelle précondition ; les nouveaux tests
D-Bus et UI testent sa vraie implémentation séparément.

## Reproduction de la validation

Depuis ce worktree :

```sh
python -B tests/session_v2/validate_keyring.py --sway /chemin/absolu/vers/sway-headless
```

Dépendances locales : Python/PyGObject/Gio, dbus-daemon, QuickShell/Qt/PySide6,
Sway pouvant démarrer headless avec pixman, outils GTK/compilateur déjà exigés
par les fixtures Session V2, kitty et grim. Aucun paquet système n'a été
installé. Le SwayFX installé ne convient pas au laboratoire sans DRM ; le
binaire Sway de test conservé par la mission précédente a été réutilisé :
`/tmp/labfy-scratchpad-tool/usr/bin/sway`. Son paquet avait le SHA-256
`5704cfc9eba9804116c665cb4450352bf5a240c1a8300b36aca3218116648443`.

Le runner impose une liste positive d'environnement, HOME et XDG privés.
Chaque test graphique réel crée son propre compositeur ; chaque service simulé
possède son bus privé. Aucun socket du bureau ni état de session utilisateur
n'est transmis. Les tests QML unitaires emploient des surfaces Item simulées et
Qt offscreen ; ils ne mappent aucune fenêtre sur un bureau réel.

La matrice couvre les 20 cas demandés : déverrouillé ; verrouillé/Prompt ;
accepté avec relecture ; annulé ; mot de passe incorrect simulé par l'absence de
fin ; fin sans déverrouillage ; timeout RPC et prompt ; service absent ; default
absent/différent et login incompatible ; redémarrage helper et vrai QuickShell ;
deux demandes concurrentes ; refus apply-last ; absence d'autorestauration ;
nouvelle session ; surface tardive ; focus final stable ; RECOVERY_REQUIRED ;
régressions scratchpad/backend/focus ; erreurs contenant une sentinelle sensible
exclue des sorties et fichiers ; login sans aide PAM. Les scénarios de mot de
passe sont simulés : aucun mot de passe réel ou d'essai n'est manipulé.

Validation finale : les onze lots réussissent (93 tests backend, 29 tests de
focus, 15 tests QML unitaires, 6 résultats Qt dont initialisation/nettoyage,
8 scénarios UI de trousseau, 2 scénarios moteur stable/tardif, recette scratchpad,
7 scénarios UI V2 existants, 5 scénarios P0 et 5 de stabilité des chemins).
Résultats et logs : `/tmp/labfy-keyring-validation-y8xyqh17/results.json` et ses
fichiers `.log`. Les chemins des laboratoires/surfaces synthétiques sont dans
ces logs. Après revue, les huit tests spécifiques D-Bus ont également été
repassés avec activation des services système désactivée dans le bus simulé :
`/tmp/labfy-keyring-privatebus-final.log`. Le test d'absence affirme NameHasOwner=false. Les avertissements PyGObject/Python de dépréciation ne sont pas des
erreurs ; aucune sortie ne contient de secret. Le runner est livré pour
reproduire les résultats si `/tmp` est nettoyé.

## Installation contrôlée et rollback

**Aucune installation n'a eu lieu.** Les fichiers de la configuration active
sont reliés aux sources du dépôt principal. Les modifier pendant que QuickShell
les surveille pourrait provoquer un rechargement. Ne pas appliquer le patch
sur ces sources pendant la session graphique réelle.

Après revue et autorisation humaine de l'intégration et de la fermeture de la
session, depuis un TTY de secours sans QuickShell actif :

1. Vérifier les changements postérieurs dans `/home/fy59/.dotfiles` et vérifier
   la base. Conserver une copie privée de tous les fichiers concernés et du
   manifeste de hashes. Ne pas toucher aux autres worktrees.
2. Examiner le patch complet livré (il inclut les nouveaux fichiers) et faire
   `git apply --check /chemin/changes.patch` depuis le dépôt principal. Un refus
   impose de réconcilier les changements ; ne jamais forcer/écraser.
3. Appliquer ce patch seulement après ce contrôle. Ne faire ni commit ni push
   automatiquement. Vérifier la résolution des liens de configuration existants,
   et `git diff --check`. Aucune modification PAM/systemd n'est à appliquer.
4. Vérifier `python -c 'from gi.repository import Gio, GLib'`. Si la dépendance
   manque, reporter l'installation ; ne pas lancer un gestionnaire de paquets
   sans autorisation. L'indisponibilité est un refus de restauration, pas un
   refus d'ouverture du bureau.
5. Au prochain login autorisé, suivre le scénario ci-dessous. Ne pas redémarrer
   le greeter ou le bureau pour « tester » depuis la session en cours.

Rollback, également hors du QuickShell actif :

```sh
cd /home/fy59/.dotfiles
git apply --reverse --check /chemin/changes.patch
git apply --reverse /chemin/changes.patch
```

En présence de dérive, restaurer seulement les fichiers sauvegardés après
comparaison avec le manifeste et revue du delta ; ne pas faire reset/restore/
stash/clean. Les fichiers nouveaux du patch doivent être retirés uniquement
si leurs hashes correspondent encore à la livraison. Aucune donnée de
checkpoint, aucun journal Recovery et aucun trousseau ne sont supprimés ou
modifiés par l'installation/rollback. PAM et systemd restent identiques.

## Prochain vrai login — autorisation humaine requise

Ce scénario est proposé et **n'a pas été exécuté** :

1. Autoriser l'intégration et une fermeture normale de la session, avec TTY de
   secours disponible ; conserver les journaux et checkpoints existants.
2. S'authentifier normalement via greetd. Sans PAM ajouté, un default verrouillé
   doit afficher Déverrouiller et Nouvelle session, sans restauration possible.
3. Déverrouiller dans le seul dialogue GNOME. N'enregistrer aucun secret et
   n'activer aucune option créant/modifiant des trousseaux. Vérifier READY et
   l'absence de lancement automatique ; cliquer ensuite explicitement Restaurer.
4. Après retrait du chooser, vérifier le rapport final : succès seulement si
   arbre **et** focus sont validés, slots et nettoyage complets. Observer le
   scratchpad sans corriger un focus inattendu pour rendre le test positif.
5. Lors d'une autre connexion autorisée, tester annulation et Nouvelle session.
   Une panne du service doit laisser ouvrir le bureau et refuser la restauration.
6. Si un prompt tardif apparaît, conserver l'échec et RECOVERY_REQUIRED,
   horodatages et identités observables. Ne jamais effacer le journal pour
   relancer artificiellement. Une trace de focus seule ne prouve pas l'auteur.
