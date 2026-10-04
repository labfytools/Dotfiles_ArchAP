import QtQuick
import Quickshell.Services.UPower
import "../components"
import "../theme"

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
                color: Theme.foreground
            }

            Text {
                anchors.left: icon.right
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                text: "Profil d'énergie"
                color: Theme.foreground
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
                    color: !available ? Theme.buttonBackground : selected ? Theme.accent : hover.hovered ? Theme.border : Theme.buttonBackground

                    Text {
                        anchors.centerIn: parent
                        text: parent.modelData.label
                        color: !parent.available ? Theme.disabledForeground : parent.selected ? Theme.onAccent : Theme.foreground
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
