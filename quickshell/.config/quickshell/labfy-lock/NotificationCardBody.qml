import QtQuick
import Quickshell

Item {
    id: body
    required property var projection
    required property color foreground
    Column {
        anchors.fill: parent; anchors.margins: 9; spacing: 5
        Text {
            width: parent.width; color: body.foreground; font.pixelSize: 13
            text: "Notifications · " + (body.projection ? body.projection.total : 0)
        }
        Repeater {
            // CONTRACT: show at most two public app counters, never private
            // notification bodies or extra fields from the projection.
            model: body.projection ? body.projection.apps.slice(0, 2) : []
            Row {
                required property var modelData
                width: parent.width; spacing: 8
                Item {
                    width: 16; height: 16
                    Image {
                        id: appIcon
                        anchors.fill: parent
                        source: modelData.icon ? Quickshell.iconPath(modelData.icon, true) : ""
                        sourceSize.width: 32; sourceSize.height: 32
                        visible: status === Image.Ready
                    }
                    Text {
                        anchors.centerIn: parent
                        visible: !appIcon.visible
                        text: ""; color: body.foreground; opacity: 0.68
                        font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 12
                    }
                }
                Text {
                    width: parent.width - 24; color: body.foreground
                    font.pixelSize: 12; elide: Text.ElideRight
                    text: modelData.name + " · " + modelData.count
                }
            }
        }
    }
}
