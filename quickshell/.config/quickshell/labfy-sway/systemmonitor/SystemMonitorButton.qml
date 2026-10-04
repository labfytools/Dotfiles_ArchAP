import QtQuick
import "../components"
import "../status"
import "../theme"

Rectangle {
    id: button
    required property bool open
    signal toggled()

    width: 26
    height: 26
    radius: 4
    color: open ? Theme.accent : pointer.containsMouse ? Theme.border : Theme.buttonBackground

    NerdIcon {
        anchors.centerIn: parent
        text: "󰍛"
        // WHY: compenser la surface plus faible du glyphe sans agrandir le bouton.
        font.pixelSize: 20
        color: button.open ? Theme.onAccent : Theme.foreground
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        onClicked: button.toggled()
    }
    StatusTooltip {
        target: button
        hovered: pointer.containsMouse && !button.open
        message: "Moniteur système"
    }
}
