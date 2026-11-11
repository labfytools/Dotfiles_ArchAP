import QtQuick
import "../theme"
Rectangle {
    id: action
    property string text: ""
    signal triggered()
    height: visible ? 30 : 0
    radius: 5
    // Keep action hover translucent over the 65%-transparent context menu.
    color: pointer.containsMouse ? Qt.rgba(Theme.buttonHover.r, Theme.buttonHover.g,
                                          Theme.buttonHover.b, 0.5) : "transparent"
    Text { anchors.fill: parent; anchors.margins: 5; text: action.text; color: Theme.foreground
        elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12 }
    MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: action.triggered() }
}
