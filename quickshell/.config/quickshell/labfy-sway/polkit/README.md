# Agent graphique Polkit V1

État au 9 octobre 2026 : l'agent QuickShell est actif. Une demande réelle a
réussi, puis une autorisation `pkexec` a permis de retirer le paquet
`polkit-gnome`, désormais inutile. `faillock` est vide après ces deux
authentifications. Les fichiers actifs avant la reprise sont sauvegardés dans
`/home/fy59/.local/state/labfy-polkit-v2-rollback-20261009/` ; ceux du premier
essai restent dans `/home/fy59/.local/state/labfy-polkit-investigation-20261009/`.

Sway ne lance plus `polkit-gnome-authentication-agent-1`. La session graphique
est SwayFX sur Wayland, et `quickshell-labfy-sway.service` lance QuickShell
sous l'utilisateur ordinaire. Son `shell.qml` possède l'unique `PolkitAgent` ;
le module natif `Quickshell.Services.Polkit` garde la file des demandes.
`PolkitDialog.qml` est créé uniquement pour le `flow` courant, sur la sortie du
workspace focalisé au début de la demande. Une sortie débranchée déclenche un
repli vers une sortie disponible. La surface layer-shell exclusive est détruite
après la demande ; un clic extérieur ne fait rien. Les panneaux de barre se
ferment et les captures automatiques Overview sont suspendues pendant la demande.

La palette vient de `Theme.qml`, elle-même alimentée par l'état effectif
`AppearanceController` et `theme/catppuccin.json`. Le dialogue suit donc les
changements de thème QuickShell. La synchronisation avec les réglages GTK/Qt
reste celle du contrôleur d'apparence existant ; aucun thème GTK supplémentaire
n'est imposé par l'agent.

`AuthFlow` fournit le message réel, l'icône, l'identifiant technique, les
identités admises, l'invite, `responseVisible`, le message complémentaire et son
état d'erreur. Une seule identité est affichée comme texte ; plusieurs passent
par un sélecteur dont les valeurs proviennent exclusivement de Polkit.
`submit()` reçoit directement le contenu du champ du flow courant lorsque
`isResponseRequired` est vrai. La réponse est effacée après soumission, échec,
changement d'identité, annulation, disparition ou remplacement du flow.
Une réponse secrète est masquée selon `responseVisible`. Le champ ne passe ni
par argv, ni par fichier, ni par IPC, ni par journal. Ceci limite les copies et
la durée de vie de la chaîne QML sans promettre un effacement physique de la
mémoire Qt. Le collage manuel reste disponible. Le succès est décidé par le
backend Polkit, jamais par l'appui sur Entrée.

Limite de l'API 0.3.1 : un changement d'identité vers une conversation ayant
exactement le même texte d'invite peut ne produire aucun signal de changement
de `inputPrompt` ni de `isResponseRequired`. Le dialogue garde alors la
soumission bloquée pendant une seconde, puis réactive le champ seulement si
le même flow, la nouvelle identité et `isResponseRequired` sont toujours
présents. Cette temporisation reste locale à la présentation et ne crée pas
de deuxième conversation ni de file de réponses. Une invite secrète vide ne
peut plus être soumise accidentellement : le champ reste modifiable, mais
Entrée et le bouton ne transmettent rien tant qu'il est vide.

L'API du paquet QuickShell 0.3.1 installé a été vérifiée dans
`/usr/lib/qt6/qml/Quickshell/Services/Polkit/quickshell-service-polkit.qmltypes`
et dans les sources de son paquet debug. `PolkitAgent` expose `isRegistered`,
`isActive`, `flow`, `authenticationRequestStarted`. `AuthFlow` expose les
propriétés ci-dessus, `submit()` et `cancelAuthenticationRequest()`. Le paquet
construit le sujet d'enregistrement depuis le PID QuickShell et annule la
requête en cours si l'agent est détruit. Si QuickShell s'arrête pendant une
demande, Polkit ne l'autorise pas par défaut : le demandeur reçoit une
annulation ou une erreur. Un redémarrage hors demande doit rétablir
`isRegistered=true`.

## Vérifications et démonstration

`PolkitVisualFixture.qml` est un shell de test autonome : il n'instancie
**aucun** `PolkitAgent`. Son IPC `polkitFixture` n'existe pas dans `shell.qml`
et ne peut pas autoriser une action Polkit. Il sert à vérifier message court ou
long, icône absente, une ou plusieurs identités, réponse visible ou masquée,
erreur et nouvelle invite, annulation et double soumission. La capture vide
[de démonstration](../../../../../docs/assets/screenshots/quickshell-polkit-demo-empty.png)
provient seulement de cette fixture, sans secret réel.

```sh
qmllint ~/.config/quickshell/labfy-sway/{shell.qml,Bar.qml,polkit/*.qml}
qs -p ~/.config/quickshell/labfy-sway/PolkitVisualFixture.qml
qs ipc -p ~/.config/quickshell/labfy-sway/PolkitVisualFixture.qml call polkitFixture checks
qs -c labfy-sway ipc call polkitUi state
```

Pour vérifier une demande réelle sans opération privilégiée, `pkcheck` peut
contrôler `org.freedesktop.timedate1.set-timezone` avec
`--process PID,START_TIME,UID --allow-user-interaction`, le PID étant celui de
Sway dans la session graphique. Ne pas ajouter `--enable-internal-agent`.
Un résultat autorisé immédiatement ne valide pas le dialogue. Aucun véritable
mot de passe n'est utilisé dans les tests automatisés ; une authentification
réelle a été validée séparément dans le dialogue local lors de la reprise.

### Premier essai

Lors de la bascule du 9 octobre 2026, la fixture a confirmé soumission unique,
erreur puis nouvelle invite, changement d'identité, disparition du flow,
deuxième demande et annulation, avec toutes les assertions à `true`. Le cas
des deux identités ayant la même invite a maintenu la soumission bloquée puis
l'a réactivée après une seconde. Les 22 tests `unittest` ciblés sur le pont
d'inhibition, l'annotation de capture et les mises à jour ont passé ;
`qmllint`, `git diff --check` et la simulation Stow ont passé. Le contrôle
`sway -C` a retourné 0 avec un avertissement EGL d'énumération GPU.

Le nouvel agent a répondu `registered=true` après l'arrêt ciblé de l'ancien.
`pkcheck` sur le sujet graphique complet `21858,320156,1000` a produit
`active=true`, `dialog=true` sur `eDP-1`. La disparition du demandeur a fermé
la surface (`active=false`, `dialog=false`). Une seconde demande a ouvert le
dialogue puis a été rejetée avec le code `3` lors d'un rechargement du shell ;
ce rechargement n'a donc accordé aucune autorisation. Un rechargement hors
demande a conservé `registered=true` avec un seul processus QuickShell.
Pendant les éditions QML suivantes, un autre rechargement hors demande a
rencontré l'erreur Wayland `xdg_popup has no parent` ; le service a redémarré
QuickShell et l'enregistrement est redevenu `true`, sans deuxième agent.
Cette erreur de popup lors d'un rechargement avec des panneaux existants reste
une limite observée de la session, sans autorisation implicite.
L'annulation par le bouton local reste à confirmer par une interaction
utilisateur hors essai d'authentification. Annuler une conversation PAM peut
consommer une tentative et ne doit pas être répété pour tester la présentation.

### Incident de verrouillage et reprise

Le premier essai a provoqué à 06:55–06:56 deux conversations Polkit échouées
sans mot de passe exploitable et une réponse refusée. `pam_faillock` a compté
trois échecs et bloqué temporairement Swaylock et `login`. Le mot de passe
n'avait pas changé. Le verrouillage a expiré et une session TTY2 a ensuite
réussi ; le redémarrage a effacé le compteur volatil. Aucune permission PAM ni
règle `sudoers` n'a été modifiée.

La reprise a utilisé d'abord `PolkitVisualFixture.qml`, sans `PolkitAgent`.
Son IPC a confirmé notamment le blocage d'une réponse secrète vide, une seule
soumission, le remplacement du flow et l'effacement du champ. Avant la demande
réelle, `faillock --user fy59` était vide et QuickShell indiquait
`registered=true`. L'utilisateur a saisi le mot de passe une seule fois dans
la fenêtre locale pour un `pkcheck` sur
`org.freedesktop.timedate1.set-timezone` ; la commande a retourné 0 sans
changer le fuseau. Le dialogue s'est fermé et `faillock` est resté vide.
Une autre demande Polkit, initiée par `pkexec` pour retirer uniquement le paquet
`polkit-gnome`, a également réussi. Aucun secret n'a été transmis à cette
conversation, à un argument de commande ou à un journal.

## Retour arrière ciblé

Le paquet GNOME a été retiré. Pour revenir à cet agent, le réinstaller depuis
un TTY (`sudo pacman -S polkit-gnome`) si l'agent QuickShell ne fonctionne pas.
Hors demande d'authentification, la copie persistante créée avant la reprise
retire ensuite l'agent QuickShell et rétablit l'autostart GNOME :

```sh
base=/home/fy59/.dotfiles
backup=/home/fy59/.local/state/labfy-polkit-v2-rollback-20261009
cp "$backup/shell.qml" "$base/quickshell/.config/quickshell/labfy-sway/shell.qml"
cp "$backup/Bar.qml" "$base/quickshell/.config/quickshell/labfy-sway/Bar.qml"
cp "$backup/WorkspaceOverview.qml" "$base/quickshell/.config/quickshell/labfy-sway/overview/WorkspaceOverview.qml"
cp "$backup/autostart" "$base/sway/.config/sway/autostart"
systemctl --user restart quickshell-labfy-sway.service
swaymsg exec /usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1
```

Ne pas lancer ce retour arrière pendant une demande active : interrompre une
conversation PAM peut consommer une tentative. Ne pas arrêter `polkitd`.
