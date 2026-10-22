import QtQuick
import "../theme"

Item {
    property string iconSource: ""
    Image {
        id: image
        anchors.fill: parent
        source: parent.iconSource
        sourceSize.width: Math.ceil(width * 2)
        sourceSize.height: Math.ceil(height * 2)
        fillMode: Image.PreserveAspectFit
        asynchronous: true
    }
    // CONTRACT: a corrupt, removed or unresolvable icon always has a visible
    // fallback independent of any installed font or desktop icon theme.
    Rectangle {
        anchors.fill: parent
        visible: image.status !== Image.Ready
        radius: width / 2; color: Theme.surface1
        border.color: Theme.lavender
        Text { anchors.centerIn: parent; text: "◇"; color: Theme.lavender; font.pixelSize: parent.width * 0.6 }
    }
}
