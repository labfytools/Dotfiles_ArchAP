import QtQuick
import "../components"
import "../status"

Rectangle {
    id: button
    required property bool open
    signal toggled()

    width: 26
    height: 26
    radius: 4
    color: open ? "#cba6f7" : pointer.containsMouse ? "#45475a" : "#313244"

    NerdIcon {
        anchors.centerIn: parent
        text: "󰍛"
        // WHY: compenser la surface plus faible du glyphe sans agrandir le bouton.
        font.pixelSize: 20
        color: button.open ? "#1e1e2e" : "#cdd6f4"
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
