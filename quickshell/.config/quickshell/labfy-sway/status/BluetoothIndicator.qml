import QtQuick
import "../components"
import "../theme"
import "StatusColorRoles.js" as StatusColorRoles

Item {
    id: indicator
    required property var adapter
    signal activated()
    width: 26
    height: 26
    readonly property var connectedDevices: adapter && adapter.devices
        ? adapter.devices.values.filter(device => device.connected) : []
    readonly property string detail: !adapter ? "Bluetooth indisponible"
        : !adapter.enabled ? "Bluetooth désactivé"
        : connectedDevices.length === 0 ? "Bluetooth activé\nAucun appareil connecté"
        : connectedDevices.length === 1 ? "Bluetooth activé\n" + connectedDevices[0].name + " connecté"
        : "Bluetooth activé\n" + connectedDevices.length + " appareils connectés\n"
            + connectedDevices.map(device => device.name).join("\n")

    Rectangle { anchors.fill: parent; radius: 4; color: pointer.containsMouse ? Theme.border : "transparent" }
    NerdIcon {
        anchors.centerIn: parent
        // WHY: le glyphe Bluetooth remplit toute la hauteur de sa police ;
        // 18 px l'aligne visuellement sur les autres statuts sans changer sa cible.
        font.pixelSize: 18
        text: indicator.adapter && indicator.adapter.enabled ? "" : "󰂲"
        // L'infobulle conserve la distinction appareil connecté / radio active.
        color: Theme[StatusColorRoles.bluetooth(!!indicator.adapter && indicator.adapter.enabled)]
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
