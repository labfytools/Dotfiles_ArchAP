# Connectivité du Control Center

Backend : QuickShell 0.3.1, `Quickshell.Networking` sur NetworkManager et
`Quickshell.Bluetooth` sur BlueZ. Les pages n'exécutent ni `nmcli` ni
`bluetoothctl` pour leurs opérations courantes.

## Wi-Fi

Le scan est possédé par la page seulement si elle active `scannerEnabled`.
À la fermeture, elle ne désactive que son propre scan. Un clic sur un réseau
connu non connecté déclenche `connect()` ; un réseau nouveau compatible
WPA/WPA2-PSK ou SAE ouvre `connectWithPsk()`. Un profil particulier est utilisé
avec `connectWithSettings()` et peut être oublié avec `NMSettings.forget()`.
L'oubli global `Network.forget()` a sa propre confirmation.

La liste « Réseaux enregistrés visibles » est limitée aux réseaux exposés par
`NetworkDevice.networks` ; l'API locale ne fournit pas de catalogue global des
profils hors de portée. Le réglage `connection.autoconnect` par profil est
reporté tant que le format de `NMSettings.read()/write()` n'a pas été confirmé
sur un profil de test. La propriété `NetworkDevice.autoconnect` est un réglage
de périphérique et ne remplace pas ce réglage par profil.

Les secrets PSK restent dans le `TextField` jusqu'à l'appel natif, puis le champ
est vidé. Aucun secret n'est enregistré ou journalisé par QuickShell.

## Bluetooth

`blueman-applet` est actif et conservé pour la prise en charge des demandes
d'authentification BlueZ (PIN, passkeys et confirmations). Son enregistrement
effectif comme agent n'a pas été éprouvé par un pairage réel. QuickShell 0.3.1 expose `pair()` et
`cancelPair()`, sans interface d'agent d'authentification dans les qmltypes
locaux. Le pairage réel demande un appareil choisi par l'utilisateur.

La découverte est activée uniquement quand la page l'initie et est arrêtée à
sa sortie. `discoverable` n'est jamais modifié automatiquement. Les opérations
`forget()`, `blocked`, `trusted`, `wakeAllowed` et l'alias local ne sont
appliquées qu'après une action explicite. `BluetoothDeviceState` n'expose que
Disconnected, Connected, Disconnecting et Connecting : les erreurs détaillées
BlueZ ne sont pas disponibles dans cette API, donc l'interface ne simule pas
un succès après un clic.
