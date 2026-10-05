import QtQuick
import "../theme"

Rectangle {
    id: button
    property string label: ""
    property bool danger: false
    signal clicked()
    implicitWidth: caption.implicitWidth + 20
    implicitHeight: 30
    radius: 4
    color: !enabled ? Theme.buttonBackground : pointer.containsMouse ? Theme.emphasisBackground : Theme.border
    opacity: enabled ? 1 : 0.55
    Text {
        id: caption
        anchors.centerIn: parent
        text: button.label
        color: button.danger ? Theme.danger : Theme.foreground
        font.pixelSize: 12
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        enabled: button.enabled
        onClicked: button.clicked()
    }
}
