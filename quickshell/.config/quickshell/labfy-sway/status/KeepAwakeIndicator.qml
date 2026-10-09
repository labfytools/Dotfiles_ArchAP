import QtQuick
import "../components"
import "../theme"

Item {
    id: indicator
    required property bool active
    required property bool unlimited
    required property int remainingSeconds
    signal activated()
    width: active ? 26 : 0
    height: 26
    visible: active

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: pointer.containsMouse ? Theme.buttonHover : Theme.emphasisBackground
    }
    NerdIcon {
        anchors.centerIn: parent
        text: "󰅶"
        font.pixelSize: 22
        color: Theme.accentForeground
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        onClicked: indicator.activated()
    }
    StatusTooltip {
        target: indicator
        hovered: pointer.containsMouse
        message: indicator.unlimited ? "Maintenir éveillé · jusqu’à désactivation"
            : "Maintenir éveillé · " + Math.ceil(indicator.remainingSeconds / 60)
                + " min restantes"
    }
}
