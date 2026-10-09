import QtQuick
import "../components"
import "../theme"

Item {
    id: page
    required property var controller
    signal backRequested()

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 10

        Item {
            width: parent.width; height: 28
            NerdIcon {
                id: backIcon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: ""
            }
            Text {
                anchors.left: backIcon.right; anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: "Maintenir éveillé"
                color: Theme.foreground
                font.pixelSize: 16; font.bold: true
            }
            MouseArea {
                anchors.left: parent.left; anchors.top: parent.top
                anchors.bottom: parent.bottom; width: 190
                onClicked: page.backRequested()
            }
        }

        Text {
            width: parent.width
            text: "Empêche le verrouillage automatique et l’extinction de l’écran."
            wrapMode: Text.Wrap
            color: Theme.secondaryForeground
            font.pixelSize: 12
        }

        Text {
            width: parent.width
            visible: page.controller.applicationRequestCount > 0
            text: "Maintien automatique demandé par une application"
            wrapMode: Text.Wrap
            color: Theme.secondaryForeground
            font.pixelSize: 12
        }

        Text {
            width: parent.width
            visible: page.controller.keepAwake
            // CONTRACT: cette durée décrit seulement la sélection manuelle ;
            // les demandes applicatives n'ont pas d'échéance connue ici.
            text: page.controller.keepAwakeMinutes === 0
                ? "Maintien manuel · jusqu’à désactivation"
                : "Maintien manuel · "
                    + Math.ceil(page.controller.keepAwakeRemainingSeconds / 60)
                    + " min restantes"
            wrapMode: Text.Wrap
            color: Theme.secondaryForeground
            font.pixelSize: 12
        }

        Repeater {
            model: [
                { label: "30 minutes", minutes: 30 },
                { label: "1 heure", minutes: 60 },
                { label: "2 heures", minutes: 120 },
                { label: "Jusqu’à désactivation", minutes: 0 }
            ]
            delegate: Rectangle {
                required property var modelData
                width: page.width; height: 44; radius: 4
                readonly property bool selected: page.controller.keepAwake
                    && page.controller.keepAwakeMinutes === modelData.minutes
                color: selected ? Theme.accent
                    : optionPointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: selected ? Theme.onAccent : Theme.foreground
                    font.pixelSize: 13
                }
                MouseArea {
                    id: optionPointer
                    anchors.fill: parent; hoverEnabled: true
                    onClicked: page.controller.setKeepAwake(modelData.minutes)
                }
            }
        }

        Rectangle {
            width: parent.width; height: 44; radius: 4
            visible: page.controller.keepAwake
            color: stopPointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
            Text {
                anchors.left: parent.left; anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: "Désactiver"
                color: Theme.foreground
                font.pixelSize: 13
            }
            MouseArea {
                id: stopPointer
                anchors.fill: parent; hoverEnabled: true
                onClicked: page.controller.clearKeepAwake()
            }
        }
    }
}
