import QtQuick
import Quickshell

PopupWindow {
    id: tip
    required property Item target
    required property string message
    property bool hovered: false
    anchor.item: target
    anchor.edges: Edges.Bottom | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    anchor.margins.bottom: -6
    visible: delay.running ? false : hovered && message.length > 0
    grabFocus: false
    color: "transparent"
    implicitWidth: Math.min(320, content.implicitWidth + 16)
    implicitHeight: content.implicitHeight + 12

    // CONTRACT: un seul délai et la même surface sont partagés par les indicateurs.
    onHoveredChanged: {
        delay.stop();
        if (hovered) delay.start();
    }
    Timer { id: delay; interval: 450; repeat: false }
    Rectangle {
        anchors.fill: parent
        radius: 4
        color: "#313244"
        border.color: "#45475a"
        Text {
            id: content
            anchors.centerIn: parent
            width: Math.min(304, implicitWidth)
            text: tip.message
            wrapMode: Text.Wrap
            color: "#cdd6f4"
            font.pixelSize: 11
        }
    }
}
