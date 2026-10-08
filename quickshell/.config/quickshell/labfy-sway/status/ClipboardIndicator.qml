import QtQuick
import "../components"
import "../theme"

Item {
    id: indicator
    required property bool open
    signal toggled()
    width: 26
    height: 26

    // CONTRACT: ce témoin ne possède aucun état d'historique ; la barre reste
    // l'unique propriétaire du LazyLoader et de l'ouverture par IPC ou clic.
    Rectangle {
        anchors.fill: parent
        radius: 4
        color: indicator.open ? Theme.accent
            : pointer.containsMouse ? Theme.border : "transparent"
    }
    NerdIcon {
        anchors.centerIn: parent
        text: "󰅇"
        font.pixelSize: 24
        color: indicator.open ? Theme.onAccent : Theme.pink
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        onClicked: indicator.toggled()
    }
    StatusTooltip {
        target: indicator
        hovered: pointer.containsMouse && !indicator.open
        message: "Presse-papiers"
    }
}
