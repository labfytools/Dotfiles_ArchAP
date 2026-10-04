import QtQuick
import "../components"

Rectangle {
    id: controlButton

    required property bool open
    signal toggled()

    width: 48
    height: 26
    radius: 4
    color: open ? "#cba6f7" : pointer.containsMouse ? "#45475a" : "#313244"

    NerdIcon {
        anchors.centerIn: parent
        text: ""
        // WHY: garder le même poids visuel que les statuts voisins dans la capsule fixe.
        font.pixelSize: 20
        color: controlButton.open ? "#1e1e2e" : "#cdd6f4"
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        onClicked: controlButton.toggled()
    }
}
