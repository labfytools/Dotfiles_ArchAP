# Nextcloud : lancement corrigé et consommation mémoire réduite

Date de validation : 27 octobre 2026, heure locale Europe/Paris.

## Résultat

Le lancement de Nextcloud depuis le menu Applications de Quickshell est corrigé et a été validé par l'ouverture d'une véritable fenêtre sur le workspace 11. Le catalogue de restauration reconnaît cette fenêtre.

La fermeture normale puis le redémarrage de l'instance de synchronisation ont réduit sa consommation immédiate : environ 4,89 Gio de mémoire résidente et de swap cumulés avant l'intervention, puis 439,4 Mio de mémoire résidente et aucun swap à 12:31:42, environ onze minutes après le redémarrage. Le service est actif et la synchronisation a repris.

**La cause durable de la forte consommation reste indéterminée.** La mémoire augmente encore pendant la synchronisation. Ces observations ne démontrent ni la disparition d'une fuite, ni l'existence d'une fuite. L'interface a également été ouverte entre les relevés. Aucune libération automatique de mémoire à la fin de la synchronisation n'est promise.

## Cause du refus de lancement

Installation observée :

- Arch : nextcloud-client 2:35.0.0-2 ;
- UWSM 0.27.1-1 ;
- entrée installée : /usr/share/applications/com.nextcloud.desktopclient.nextcloud.desktop ;
- commande de l'entrée : nextcloud %u.

Le validateur d'UWSM a été appelé sur cette entrée et a reproduit le refus. Il rejetait le groupe org.freedesktop.CloudProviders et les métadonnées Implements, BusName et ObjectPath. La validation indépendante avec desktop-file-validate a terminé avec le code 0. Le problème observé concerne donc le chemin de lancement via l'ancien validateur de métadonnées d'UWSM.

## Correction du lanceur

Fichier : quickshell/.config/quickshell/labfy-sway/applications/backend.py.

La fonction uwsm_launch_info construit une copie en mémoire de l'entrée Desktop et préfixe sa commande par « uwsm app -t service -- ». GIO conserve la gestion des arguments et des champs Desktop. Le chemin de l'entrée d'origine est conservé pour le champ %k. La copie désactive Terminal et DBusActivatable pour ce chemin de lancement. Le fichier installé et ses métadonnées CloudProviders restent intacts.

Le nouveau chemin est réservé à l'identifiant exact com.nextcloud.desktopclient.nextcloud.desktop. Les autres applications graphiques conservent leur chemin existant. L'ancien traitement des applications de terminal utilise le même helper avec son option de terminal, et le correctif antérieur de lecture des exécutables entre guillemets est préservé.

Le validateur UWSM lui-même n'a pas été modifié globalement.

## Validation du lancement

Les 16 tests de tests/applications/test_backend.py passent. Ils couvrent notamment :

- l'aiguillage du seul identifiant Nextcloud vers le nouveau chemin ;
- la conservation des métadonnées et du fichier Desktop source ;
- le lancement GIO réel vers un enregistreur UWSM de test, avec guillemets, espaces, champs Desktop et répertoire de travail ;
- les erreurs de lancement et les chemins existants de terminal, D-Bus et filtrage d'applications.

Essai réel à 12:22:26 :

- appel du backend avec « launch com.nextcloud.desktopclient.nextcloud.desktop » ;
- réponse ok, code de sortie 0, stderr vide ;
- fenêtre Nextcloud observée : con_id 95, app_id com.nextcloud.desktopclient.nextcloud ;
- processus 1061535, starttime 43226650, workspace 11 ;
- classification correcte par le catalogue de session ;
- huit fenêtres préexistantes conservées dans leur état vérifié ;
- sauvegarde automatique canonique inchangée.

La fenêtre Nextcloud reste disponible sur le workspace 11. Le retour du focus au workspace 1 n'a pas été imposé : au dernier contrôle, le focus n'était plus sur la fenêtre de test.

## Intervention sur la mémoire

L'ancienne instance était l'unique processus Nextcloud, PID 982359, lancé en arrière-plan par app-Nextcloud@autostart.service. Son activité de synchronisation progressait ; la forte consommation n'était pas associée à un arrêt complet du traitement dans les échantillons examinés.

À 12:20:36, « /usr/bin/nextcloud --quit » a été exécuté dans l'environnement graphique. Le processus s'est arrêté normalement. Le service est devenu inactif avec Result=success et ExecMainStatus=0.

À 12:20:45, le même service utilisateur app-Nextcloud@autostart.service a été démarré. Son nouveau processus est 1061535. Aucune seconde instance permanente n'a été créée.

| Relevé local | RAM résidente | Swap |
|---|---:|---:|
| 12:18:57, avant redémarrage | 2 289 668 Kio | 2 837 904 Kio |
| 12:22:04 | 332 768 Kio, soit 325,0 Mio | 0 |
| 12:24:06 | 372 024 Kio, soit 363,3 Mio | 0 |
| 12:26:27 | 403 424 Kio, soit 393,9 Mio | 0 |
| 12:31:42 | 449 960 Kio, soit 439,4 Mio | 0 |

Les valeurs avant intervention représentent environ 2,18 Gio de RAM et 2,71 Gio de swap, soit 4,89 Gio cumulés. Cette somme sert à comparer les deux composantes relevées ; elle n'est pas une mesure de RAM résidente seule.

La propriété CloudProviders Status a été lue sur le propriétaire D-Bus du nouveau processus et indiquait SYNCING. Dans l'échantillon des journaux de 12:27:55 à 12:28:13, l'activité de retraits locaux était présente, avec 301 mentions de succès et aucune des mentions d'erreur NormalError, FatalError ou SoftError recherchées. Cela prouve une progression dans cet intervalle, pas l'achèvement de toute la synchronisation.

Le dernier relevé confirme le même processus et un service active/running, Result=success.

Aucun plafond mémoire, changement de parallélisme, exclusion de synchronisation, changement de base de données ou mise à jour de paquet n'a été appliqué. La cause n'étant pas établie, ces changements ne constituent pas une correction démontrée. Aucune terminaison forcée n'a été nécessaire.

## Limite restante

Une nouvelle mesure après retour effectif de la synchronisation au repos sera nécessaire pour distinguer la mémoire de travail du lot actif d'une croissance persistante. Il n'existe pas de surveillance permanente installée par cette intervention. Le redémarrage a résorbé la surconsommation présente ; il ne remplace pas un diagnostic de récurrence.

## Liens avec la restauration de session

La restauration autorisée a réussi auparavant, à 12:10:59, transaction 335bf44840674810b4761ade767f31db : sept fenêtres restaurées, arbre et focus validés. Une capture de diagnostic indépendante a ensuite reconnu les huit fenêtres ouvertes, Proton Pass compris. La session a été acquittée comme restaurée.

La sauvegarde automatique conservée reste :

/home/fy59/.local/state/labfy-sway/session-v2/automatic/last.json

SHA-256 : 9a36bb310f48d989a8763092ae220a974a00786da6fba2c86dc25e7cfed1cd89

La fenêtre Nextcloud ouverte pour le test est postérieure à cette sauvegarde. Aucune nouvelle restauration ni déconnexion de session n'a été exécutée pendant l'intervention Nextcloud.

## Preuves et sauvegarde du code

Dossier privé des preuves :

/home/fy59/.local/state/labfy-sway/session-v2-diagnostics/20261027-120604-focus-catalog-restore

Fichiers principaux : nextcloud-launch-deployment.json, nextcloud-launch-tests.log, nextcloud-graceful-stop-result.json, nextcloud-background-restart-result.json, nextcloud-real-launch-result.json, nextcloud-sync-progress-after-restart.json, nextcloud-closeout-sample.json.

Sauvegarde préalable du code :

/home/fy59/.local/state/labfy-sway/session-v2-code-backups/20261027-121930-nextcloud-launch

Empreintes déployées :

- applications/backend.py : 9a335d9c99e8c3561f07123f6946207dfceab1aa25d0ec68b28d6e42975cb918 ;
- tests/applications/test_backend.py : 96ef887fa4757dcf6f4b06f61c1ea12b8dee95dfb4261e1c78e876c4edd349a6.

Les modifications sont présentes dans le dépôt actif et dans le worktree session-v2-desktop-apps-20261027. Aucun commit ni push n'a été effectué.
