import QtQuick
import QtQuick.Controls
import "../applications"
import "../theme"

// A selectable, keyboard-focusless preview of one existing Sway toplevel.
// A missing/failed screencopy falls back to the corresponding app icon.
Rectangle {
    id: card
    required property var windowData
    property string iconSource: ""
    property string imageSource: ""
    signal activated()

    width: 190
    height: 148
    radius: 8
    color: Qt.rgba(Theme.surface0.r, Theme.surface0.g, Theme.surface0.b, 0.8)
    border.color: pointer.containsMouse ? Theme.lavender : Theme.strongBorder
    border.width: pointer.containsMouse ? 2 : 1
    Item {
        id: shotArea
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 7
        height: 99
        clip: true
        Rectangle { anchors.fill: parent; radius: 5; color: Theme.mantle }
        Image {
            id: shot
            anchors.fill: parent
            source: card.imageSource
            cache: false
            asynchronous: true
            fillMode: Image.PreserveAspectFit
            visible: status === Image.Ready
        }
        ApplicationIcon {
            anchors.centerIn: parent
            width: 46
            height: 46
            visible: shot.status !== Image.Ready
            iconSource: card.iconSource
        }
    }
    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: shotArea.bottom
        anchors.topMargin: 3
        anchors.leftMargin: 7
        anchors.rightMargin: 7
        text: card.windowData.title || "Fenêtre"
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: Theme.foreground
        font.pixelSize: 11
    }
    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 7
        anchors.rightMargin: 7
        anchors.bottomMargin: 3
        text: "Workspace " + (card.windowData.workspace || "?")
        elide: Text.ElideRight
        color: Theme.secondaryForeground
        font.pixelSize: 10
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: card.activated()
        ToolTip.visible: containsMouse
        ToolTip.text: card.windowData.title || "Fenêtre"
        ToolTip.delay: 650
    }
}
