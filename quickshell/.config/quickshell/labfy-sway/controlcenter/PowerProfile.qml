import QtQuick
import Quickshell.Services.UPower
import "../components"

Item {
    id: powerControl

    implicitHeight: content.implicitHeight

    Column {
        id: content
        width: parent.width
        spacing: 12

        Item {
            width: parent.width
            height: 28

            NerdIcon {
                id: icon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: ""
                font.pixelSize: 18
                color: "#cdd6f4"
            }

            Text {
                anchors.left: icon.right
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                text: "Profil d'énergie"
                color: "#cdd6f4"
                font.pixelSize: 14
            }
        }

        Row {
            id: choices
            width: parent.width
            height: 34
            spacing: 4

            Repeater {
                model: [
                    { label: "Économie", profile: PowerProfile.PowerSaver },
                    { label: "Équilibré", profile: PowerProfile.Balanced },
                    { label: "Performance", profile: PowerProfile.Performance }
                ]

                Rectangle {
                    required property var modelData
                    readonly property bool available: modelData.profile !== PowerProfile.Performance
                        || PowerProfiles.hasPerformanceProfile
                    readonly property bool selected: PowerProfiles.profile === modelData.profile

                    width: (choices.width - 2 * choices.spacing) / 3
                    height: choices.height
                    radius: 4
                    color: !available ? "#313244" : selected ? "#cba6f7" : hover.hovered ? "#45475a" : "#313244"

                    Text {
                        anchors.centerIn: parent
                        text: parent.modelData.label
                        color: !parent.available ? "#6c7086" : parent.selected ? "#1e1e2e" : "#cdd6f4"
                        font.pixelSize: 12
                    }

                    HoverHandler { id: hover }

                    MouseArea {
                        anchors.fill: parent
                        enabled: parent.available
                        acceptedButtons: Qt.LeftButton
                        onClicked: PowerProfiles.profile = parent.modelData.profile
                    }
                }
            }
        }
    }
}
