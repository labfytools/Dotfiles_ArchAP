# OSD volume, luminosité et microphone

`OsdService` observe le sink PipeWire par défaut via le `VolumeSlider` déjà
partagé entre la barre et le Control Center. Il observe le rétroéclairage via
le `BrightnessSlider` existant, et suit en plus le nœud source PipeWire par
défaut avec `PwObjectTracker`, même si la page Audio n'a jamais été ouverte.
Ce dernier suivi ne crée aucun flux de capture. Les touches Sway gardent leurs
commandes `pactl` et `brightnessctl`, leurs pas et leurs bornes. Le défilement
de la barre utilise toujours les mêmes curseurs. Un changement externe des
mêmes valeurs est également détecté. Les flux d'applications du mixeur ne
déclenchent rien.

Chaque nouvelle identité de périphérique et chaque reconnexion établissent
une référence sans affichage. Une valeur brute identique est ignorée ; la
carte présente la valeur observée après confirmation, y compris un volume
externe supérieur à 100 %. Seule la jauge est plafonnée. Une valeur
indisponible ne devient pas `0 %`. Le microphone indique `Muet` ou `Non muet`,
sans prétendre détecter une capture active. Lorsqu'un contrôle correspondant
est visible dans un Control Center, l'OSD est supprimé. Toute carte active est
fermée dès le début d'une authentification Polkit, sans rejeu ultérieur.

La surface `labfy-setting-osd` est une seule `PanelWindow` de 320 × 80 pixels
logiques au maximum, centrée en bas à environ 40 pixels de la sortie choisie.
Son fond reprend `Theme.popupBackground` à 92 % d'opacité.
Une action de barre privilégie sa sortie ; les autres changements suivent le
moniteur focalisé de `I3`, avec repli sur la première sortie disponible.
Elle est sur la couche `Overlay`, au-dessus d'un contenu plein écran, avec
`WlrKeyboardFocus.None`, zone d'exclusion ignorée et région d'entrée Wayland
vide. Elle ne prend donc ni focus ni entrée pointeur. Sa création n'ouvre ni
panneau, ni notification, ni `IdleInhibitor` ; la tasse et le pont Firefox ne
sont pas liés à cette surface.

Chaque événement pertinent remplace le contenu de la carte et relance son
délai de 1500 ms. Une génération de minuteur empêche une ancienne échéance
de fermer une carte plus récente. La surface est détruite à l'expiration.
L'Overview évite de capturer cette surface sans supprimer ses miniatures
existantes.

`node tests/quickshell/test_osd_observation.js` vérifie les références, les
changements, les rafales, les échéances, la sourdine synthétique et le choix de
sortie. `OsdVisualFixture.qml` montre une luminosité fictive de 42 % ; sa
[capture recadrée](../../../../../docs/assets/screenshots/quickshell-osd-synthetic-brightness.png)
ne contient aucune donnée personnelle.
