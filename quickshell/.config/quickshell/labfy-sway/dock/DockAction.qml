import QtQuick
import "../theme"
Rectangle {
    id: action
    property string text: ""
    signal triggered()
    height: visible ? 30 : 0
    radius: 5
    color: pointer.containsMouse ? Theme.buttonHover : "transparent"
    Text { anchors.fill: parent; anchors.margins: 5; text: action.text; color: Theme.foreground
        elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12 }
    MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: action.triggered() }
}
