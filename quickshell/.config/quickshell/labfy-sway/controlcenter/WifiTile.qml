import QtQuick
import Quickshell.Networking

QuickToggle {
    id: tile
    required property var wifiDevice

    readonly property var connectedNetwork: wifiDevice && wifiDevice.networks
        ? wifiDevice.networks.values.find(network => network.connected) : null

    title: "Wi-Fi"
    icon: Networking.wifiEnabled && Networking.wifiHardwareEnabled ? "󰖩" : "󰖪"
    active: Networking.wifiEnabled && Networking.wifiHardwareEnabled
    toggleEnabled: wifiDevice !== null && Networking.wifiHardwareEnabled
    subtitle: !Networking.wifiHardwareEnabled ? "Bloqué matériellement"
        : !Networking.wifiEnabled ? "Désactivé"
        : connectedNetwork ? connectedNetwork.name : "Non connecté"

    // Le blocage matériel ne peut pas être levé par le bouton logiciel.
    onToggleRequested: {
        if (Networking.wifiHardwareEnabled && wifiDevice)
            Networking.wifiEnabled = !Networking.wifiEnabled;
    }
}
