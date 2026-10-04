import QtQuick
import "../components"
import "../theme"

Rectangle {
    id: controlButton

    required property bool open
    signal toggled()

    width: 48
    height: 26
    radius: 4
    color: open ? Theme.accent : pointer.containsMouse ? Theme.border : Theme.buttonBackground

    NerdIcon {
        anchors.centerIn: parent
        text: ""
        // WHY: garder le même poids visuel que les statuts voisins dans la capsule fixe.
        font.pixelSize: 20
        color: controlButton.open ? Theme.onAccent : Theme.foreground
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        onClicked: controlButton.toggled()
    }
}
