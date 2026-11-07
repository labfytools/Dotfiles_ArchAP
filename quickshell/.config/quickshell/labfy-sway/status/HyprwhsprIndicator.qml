import QtQuick
import "../components"
import "../theme"

Item {
    id: indicator
    required property var service
    property bool authenticationActive: false
    width: 26; height: 26
    Rectangle {
        anchors.fill: parent
        radius: 4
        color: pointer.containsMouse ? Theme.buttonHover : "transparent"
    }
    NerdIcon {
        anchors.centerIn: parent
        font.pixelSize: 18
        text: indicator.service.state === "error" ? "󰀪" : "󰍬"
        color: indicator.service.state === "error" || indicator.service.state === "recording"
            ? Theme.red : indicator.service.state === "processing" ? Theme.yellow : Theme.overlay2
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: {
            if (!indicator.authenticationActive && !indicator.service.commandBusy)
                indicator.service.toggle();
        }
    }
    StatusTooltip {
        target: indicator
        hovered: pointer.containsMouse && !indicator.authenticationActive
        message: indicator.service.tooltip
    }
}
