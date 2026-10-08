import QtQuick
import "../components"
import "../theme"

Rectangle {
    id: controlButton

    required property bool open
    signal toggled()

    // Même hauteur que les actions voisines, avec une cible légèrement plus
    // large pour l'accès au panneau sans capsule permanente.
    width: 30
    height: 26
    radius: 4
    color: open ? Theme.emphasisBackground : pointer.containsMouse ? Theme.border : "transparent"

    NerdIcon {
        anchors.centerIn: parent
        text: ""
        // WHY: garder le même poids visuel que les actions voisines sans capsule permanente.
        font.pixelSize: 28
        color: controlButton.open ? Theme.accentForeground : Theme.lavender
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        onClicked: controlButton.toggled()
    }
}
