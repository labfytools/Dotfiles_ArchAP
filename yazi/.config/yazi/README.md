# Yazi : supports amovibles et espace disque

Configuration suivie par GNU Stow (`stow yazi`). Yazi 26.9.1 est requis.

## Supports

`devices.yazi` affiche un résumé au-dessus du panneau parent. La zone reste
informative : l'API du panneau parent ne fournit pas une liste indépendante
avec son propre curseur. Le menu `M` permet de choisir un support et une action :
ouvrir, monter puis ouvrir, démonter ou retirer en sécurité. Le montage d'un
support non monté demande confirmation. Les erreurs sont affichées par Yazi.

La source de vérité est `labfy-removable-media.service`, déjà fourni par ces
dotfiles avec `labfy-removable-mediactl`. Le service utilise UDisks2 pour les
volumes bloc et Gio/GVfs pour MTP. Il élimine les partitions système et les
montages techniques. Installer `udisks2`, `gvfs` et `gvfs-mtp` sur Arch ;
`udiskie` n'est pas requis. Le service et sa commande doivent être installés via
les paquets Stow `systemd` et `bin`. La liste est relue toutes les cinq secondes
par une tâche Lua de l'instance Yazi ; aucun `lsblk` n'est lancé au rendu.
Le service réagit lui-même aux changements UDisks2/Gio. L'espace libre des
volumes bloc montés est lu avec `df` au plus toutes les trente secondes. MTP est
présenté comme MTP, sans capacité inventée.

La colonne de gauche passe à 20 % de la largeur. Sous 17 colonnes, le résumé
est masqué afin de préserver le panneau parent. Sa hauteur est bornée à huit
lignes ; si beaucoup de supports sont connectés, `M` donne accès à la liste
complète. Les clics dans le résumé n'activent aucun périphérique.

## Espace disque

`disk-space.yazi` lit `df -B1 --output=size,avail -- <cwd>` en tâche
asynchrone au changement de répertoire. `avail` correspond à l'espace
utilisable par l'utilisateur courant, selon la réponse du système de fichiers. La capacité et l'espace libre sont affichés en unités
IEC. Si `df` échoue, la barre indique « Espace indisponible ». Le reste de la
barre de statut, notamment les ajouts existants, reste configuré dans
`init.lua`.

`sduf.yazi` a été évalué : il indique l'espace utilisé sur la capacité totale,
avec analyse de `df -h`, ce qui ne répond pas au besoin d'espace réellement
disponible. `mount.yazi` est compatible avec Yazi 26.9.1 mais n'apporte ni
panneau permanent filtré ni MTP. `gvfs.yazi` annonce ne plus être maintenu ;
aucun de ces trois plugins n'est installé.

## Vérification visuelle

Lancer `yazi`, brancher ou débrancher un support et attendre au plus cinq
secondes. Vérifier le panneau, puis `M`. Pour un volume monté, choisir son
numéro puis `o`. Pour un volume non monté, choisir `m` et confirmer ; `u` et `e`
sont des opérations explicites. Vérifier l'espace libre après navigation vers
un autre système de fichiers. Ne pas démonter ni éjecter un support en cours
d'utilisation.
