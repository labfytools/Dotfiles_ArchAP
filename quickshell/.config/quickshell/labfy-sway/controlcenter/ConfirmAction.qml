import QtQuick
import "../theme"

Item {
    id: confirmation

    required property var actionInfo
    signal cancelled()
    signal confirmed(string actionId)

    implicitHeight: Math.max(120, content.implicitHeight)

    Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 16

        Text {
            width: parent.width
            text: confirmation.actionInfo.confirmTitle
            color: Theme.foreground
            font.pixelSize: 16
            font.bold: true
            wrapMode: Text.Wrap
        }

        Text {
            width: parent.width
            text: confirmation.actionInfo.description
            color: Theme.secondaryForeground
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }

        Row {
            width: parent.width
            height: 34
            spacing: 8

            Rectangle {
                width: (parent.width - parent.spacing) / 2
                height: parent.height
                radius: 4
                color: cancelPointer.containsMouse ? Theme.border : Theme.buttonBackground

                Text {
                    anchors.centerIn: parent
                    text: "Annuler"
                    color: Theme.foreground
                    font.pixelSize: 13
                }
                MouseArea {
                    id: cancelPointer
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton
                    onClicked: confirmation.cancelled()
                }
            }

            Rectangle {
                width: (parent.width - parent.spacing) / 2
                height: parent.height
                radius: 4
                color: confirmation.actionInfo.accent

                Text {
                    anchors.centerIn: parent
                    text: confirmation.actionInfo.label
                    color: Theme.contrastingText(confirmation.actionInfo.accent)
                    font.pixelSize: 13
                    font.bold: true
                }
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton
                    onClicked: confirmation.confirmed(confirmation.actionInfo.id)
                }
            }
        }
    }
}
