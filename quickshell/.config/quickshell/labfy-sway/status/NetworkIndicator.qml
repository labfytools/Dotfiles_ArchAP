import QtQuick
import Quickshell.Networking
import "../components"
import "../theme"

Item {
    id: indicator
    required property var wifiDevice
    signal activated()
    width: 26
    height: 26
    readonly property var connectedNetwork: wifiDevice && wifiDevice.networks
        ? wifiDevice.networks.values.find(network => network.connected) : null
    readonly property int signalPercent: connectedNetwork
        ? Math.round(Math.max(0, Math.min(1, connectedNetwork.signalStrength)) * 100) : 0
    readonly property string detail: !Networking.wifiHardwareEnabled
        ? "Wi-Fi\nBloqué matériellement"
        : !Networking.wifiEnabled ? "Wi-Fi\nDésactivé"
        : !wifiDevice ? "Wi-Fi\nPériphérique indisponible"
        : !connectedNetwork ? "Wi-Fi\nNon connecté"
        : "Wi-Fi\n" + connectedNetwork.name + "\nSignal : " + signalPercent + " %"

    Rectangle { anchors.fill: parent; radius: 4; color: pointer.containsMouse ? Theme.border : "transparent" }
    NerdIcon {
        anchors.centerIn: parent
        // WHY: md-wifi remplit mieux la hauteur visuelle que les quatre glyphes
        // de niveau ; le pourcentage exact reste disponible dans le tooltip.
        font.pixelSize: 26
        // CONTRACT: les glyphes connecté, déconnecté et off existent dans la
        // Nerd Font installée ; seul l'état connecté est simplifié dans la barre.
        text: !Networking.wifiHardwareEnabled ? "󰖪"
            : !Networking.wifiEnabled ? "󰖪"
            : !indicator.connectedNetwork ? "󰤯" : "󰖩"
        color: !Networking.wifiHardwareEnabled ? Theme.danger
            : !Networking.wifiEnabled ? Theme.secondaryForeground : Theme.foreground
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: indicator.activated()
    }
    StatusTooltip { target: indicator; hovered: pointer.containsMouse; message: indicator.detail }
}
