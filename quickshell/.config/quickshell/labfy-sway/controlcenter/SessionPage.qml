import QtQuick
import Quickshell
import "../components"
import "../theme"

Item {
    id: page

    required property var actions
    signal backRequested()
    signal actionRequested(string actionId)

    // La taille doit être connue avant la création des delegates pour éviter un popup de hauteur nulle.
    implicitHeight: 28 + actions.length * 48 + actions.length * 10

    Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 10

        Item {
            width: parent.width
            height: 28

            NerdIcon {
                id: backIcon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: ""
            }
            Text {
                anchors.left: backIcon.right
                anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: "Session"
                color: Theme.foreground
                font.pixelSize: 16
                font.bold: true
            }
            MouseArea {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 100
                acceptedButtons: Qt.LeftButton
                onClicked: page.backRequested()
            }
        }

        Repeater {
            model: page.actions
            delegate: SessionAction {
                required property var modelData
                width: content.width
                actionInfo: modelData
                onSelected: actionId => page.actionRequested(actionId)
            }
        }
    }
}
