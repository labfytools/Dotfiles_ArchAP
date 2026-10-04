# Helper de limite de charge

La source suivie est `usr/local/sbin/batlimit-set` dans ce répertoire. Le fichier
exécuté via la règle sudoers existante est `/usr/local/sbin/batlimit-set`.

Déploiement administrateur après revue :

```sh
sudo install -o root -g root -m 0755 \
  /home/fy59/.dotfiles/bin/root/usr/local/sbin/batlimit-set \
  /usr/local/sbin/batlimit-set
```

Le helper crée et maintient `/etc/tlp.d/90-labfy-charge-limit.conf` en
`root:root` et mode `0644`. Ce fichier contient la préférence persistante et
n'est pas suivi par Git. La configuration antérieure
`/etc/tlp.d/10-archasp.conf` reste intacte avec le seuil de secours à 60 %.

Le helper accepte exactement un entier de 40 à 100. Il affiche `SUCCESS X`
avec le code 0 seulement après relecture du seuil sysfs. Il affiche
`ERROR invalid_value` (code 2), `ERROR unavailable` ou
`ERROR apply_failed` (code 1), ou `ERROR rollback_failed` (code 3).
Une erreur d'application restaure l'ancien fichier et tente de réappliquer
l'ancien seuil. `rollback_failed` exige une vérification administrative de
la configuration et du seuil sysfs.

`~/.local/bin/batlimit` est la CLI utilisateur suivie par GNU Stow via
`bin/.local/bin/batlimit`. Sans argument elle garde l'invite historique ; avec
un entier (`batlimit 80`) elle appelle le même helper privilégié que la page
Batterie de QuickShell. La CLI affiche un compte rendu lisible, tandis que
QuickShell appelle directement le helper et vérifie sa sortie structurée.
Le wrapper ne modifie ni sysfs ni TLP lui-même.

Rollback administrateur après revue :

```sh
sudo rm /etc/tlp.d/90-labfy-charge-limit.conf
sudo tlp start
cat /sys/class/power_supply/BAT1/charge_control_end_threshold
```

Après le prochain démarrage, vérifier le seuil avec la même lecture sysfs,
ainsi que `sudo tlp-stat -b` et `journalctl -u tlp.service -b`.
