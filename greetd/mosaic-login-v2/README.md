# Récupération de connexion Mosaic + QuickShell V2

État : EXPERIMENTAL / **READY_FOR_EXPLICIT_INSTALL_APPROVAL**. Audit r1 FAIL
conservé ; réparation et revue bornée indépendante r2 PASS. Sources candidates uniquement ; aucune
installation ni activation. Le ticket V2 complète le sélecteur V1 conservé.

Contrat : greetd/PAM choisit un argv fixe Stable ou Mosaic. Le lanceur conserve
les contrôles de fichiers, logind, VT, cgroup et absence de parent graphique.
Le parsing des propriétés systemd doit restituer les unités escapées et vérifier
Id, LoadState, DropInPaths et les exclusions réellement chargées.

UWSM est propriétaire du compositeur autonome. Son finalize exporte ses sockets
avant READY=1 ; QuickShell est ordonné après le target et le WM notify. Une garde
refuse un autre WM/QuickShell et valide PID, binaire, provider et sockets avant
le lancement. PartOf/BindsTo attachent son arrêt au target Mosaic. Aucune relance
automatique, aucun autostart XDG/idle/clipboard/gamma ou restore V2 dans ce smoke.

Les sources ici ne sont pas stowées et ne modifient pas les fichiers actifs.
Le bundle séparera root greeter et utilisateur, avec sauvegardes durables,
préflight global, journal/reprise et rollback sans dépendance au LAB. Le test
physique, la barre réelle et le retour greetd restent NOT_RUN avant approbation.

Procédure, résultats bruts et limites : [LOGIN_RECOVERY_V2](../LOGIN_RECOVERY_V2.md).
