import QtQuick

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
            color: "#cdd6f4"
            font.pixelSize: 16
            font.bold: true
            wrapMode: Text.Wrap
        }

        Text {
            width: parent.width
            text: confirmation.actionInfo.description
            color: "#a6adc8"
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
                color: cancelPointer.containsMouse ? "#45475a" : "#313244"

                Text {
                    anchors.centerIn: parent
                    text: "Annuler"
                    color: "#cdd6f4"
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
                    color: "#1e1e2e"
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
