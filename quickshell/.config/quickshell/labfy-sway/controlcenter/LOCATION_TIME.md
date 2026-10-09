# Localisation & heure

La page **Réglages rapides → Apparence → Localisation & heure** sépare le fuseau horaire système de la position solaire utilisée par wlsunset. Le fuseau vient exclusivement de `timedatectl` ; les coordonnées, les lieux enregistrés et le nom actif facultatif viennent de `~/.config/labfy-appearance/preferences.json` (mode 0600). Aucun service réseau, aucune détection IP et aucun lieu personnel ne font partie du dépôt.

## Données locales et voyage

`location-time-manager.py` lit `/usr/share/zoneinfo/zone1970.tab`, convertit ses coordonnées compactes et vérifie les identifiants dans `/usr/share/zoneinfo`. La recherche est locale et instantanée. Les coordonnées de cette base sont des points représentatifs associés aux fuseaux ; elles ne sont pas forcément la position exacte de l'utilisateur. La position manuelle accepte une latitude de −90 à 90 et une longitude de −180 à 180. La liste facultative `savedLocations` est limitée à 100 entrées validées et permet de réutiliser un choix, mais ouvre toujours un résumé avant application. `activeLocationName` est un libellé facultatif sans effet sur le calcul.

Une sélection propose **Appliquer les deux**, **Fuseau uniquement** et **Position solaire uniquement**. Le clic dans la liste ne change rien. La préférence de thème, le fond d'écran et le mode Night Light ne changent pas. Le nom actif n'est qu'un libellé d'interface.

## Privilèges et transaction

`timedatectl set-timezone` est appelé directement, avec un tableau d'arguments,
via l'authentification Polkit standard de la session. L'agent graphique natif
QuickShell présente la demande locale : sa fenêtre reçoit temporairement la
réponse masquée, la transmet à `AuthFlow.submit()` et efface le champ. Elle ne
l'écrit ni dans un argument, ni dans un fichier, ni dans un journal. QuickShell
ne dispose d'aucune permission root permanente et ne modifie jamais
`/etc/localtime` directement. Si l'authentification est annulée ou
indisponible, l'opération échoue sans écrire la position solaire.

L'application combinée valide d'abord les entrées, mémorise l'état précédent, change le fuseau, écrit la position locale, réconcilie Night Light en Auto, puis vérifie le fuseau. Un échec de fuseau laisse la position intacte. Un échec ultérieur restaure la préférence et tente de restaurer le fuseau et le service. Un échec de rollback est affiché comme erreur explicite.

## Night Light et persistance

En Auto hors Mode Soleil, la nouvelle position redémarre l'unique `wlsunset.service`. En mode Activée, la température forcée reste active et la position est seulement enregistrée. En mode Désactivée ou pendant le Mode Soleil, aucune instance n'est démarrée. À la sortie du Mode Soleil ou à la prochaine session Auto, wlsunset relit la nouvelle position. Changer seulement le fuseau ne modifie jamais les coordonnées : wlsunset utilise le temps système et les coordonnées, pas une association implicite ville/fuseau.

Le fuseau persiste via `systemd-timedated`, la position via les préférences. En mode solaire, le [code de wlsunset](https://github.com/kennylevinsen/wlsunset/blob/master/main.c) déduit le jour de la longitude et calcule les événements avec l'heure système UTC ; son décalage de fuseau n'est utilisé que pour l'horaire manuel (`longitude_time_offset` et `wlrun`). Un changement de fuseau seul ne nécessite donc pas de redémarrer Auto ni de modifier les coordonnées. `SystemClock` est rafraîchi à la publication d'un changement de fuseau et continue son tick minute normal. Aucun paramètre horaire propre à Firefox, Kitty, Neovim, GTK ou Qt n'est écrit.
