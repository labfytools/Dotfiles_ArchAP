import QtQuick
import "../components"
import "../theme"

Rectangle {
    id: actionButton

    required property var actionInfo
    signal selected(string actionId)

    height: 48
    radius: 4
    color: pointer.containsMouse ? Theme.border : Theme.buttonBackground

    NerdIcon {
        id: icon
        anchors.left: parent.left
        anchors.leftMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        width: 22
        text: actionButton.actionInfo.icon
        color: actionButton.actionInfo.accent
        font.pixelSize: 18
    }

    Text {
        anchors.left: icon.right
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        text: actionButton.actionInfo.label
        color: Theme.foreground
        font.pixelSize: 14
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: actionButton.selected(actionButton.actionInfo.id)
    }
}
