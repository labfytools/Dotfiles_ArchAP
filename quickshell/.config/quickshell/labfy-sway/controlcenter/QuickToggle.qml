import QtQuick
import "../components"

Rectangle {
    id: tile

    required property string title
    required property string subtitle
    required property string icon
    required property bool active
    property bool toggleEnabled: true
    signal toggleRequested()
    signal detailsRequested()

    height: 58
    radius: 4
    color: active ? "#cba6f7" : "#313244"
    readonly property color foreground: active ? "#1e1e2e" : "#cdd6f4"

    NerdIcon {
        id: symbol
        anchors.left: parent.left
        anchors.leftMargin: 11
        anchors.verticalCenter: parent.verticalCenter
        text: tile.icon
        color: tile.foreground
        font.pixelSize: 19
    }

    Column {
        anchors.left: symbol.right
        anchors.leftMargin: 9
        anchors.right: chevron.left
        anchors.rightMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1

        Text {
            width: parent.width
            text: tile.title
            color: tile.foreground
            font.pixelSize: 13
            font.bold: true
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: tile.subtitle
            color: tile.foreground
            opacity: 0.82
            font.pixelSize: 11
            elide: Text.ElideRight
        }
    }

    Item {
        id: chevron
        anchors.right: parent.right
        width: 28
        height: parent.height

        NerdIcon {
            anchors.centerIn: parent
            text: ""
            color: tile.foreground
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            onClicked: tile.detailsRequested()
        }
    }

    MouseArea {
        anchors.left: parent.left
        anchors.right: chevron.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        enabled: tile.toggleEnabled
        acceptedButtons: Qt.LeftButton
        onClicked: tile.toggleRequested()
    }
}
