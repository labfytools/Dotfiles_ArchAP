import QtQuick
import "../theme"

Rectangle {
    id: button
    required property string text
    signal clicked()
    implicitWidth: label.implicitWidth + 18
    implicitHeight: 28
    radius: 4
    opacity: enabled ? 1 : 0.5
    color: mouse.containsMouse ? Theme.buttonHover : Theme.buttonBackground
    border.color: activeFocus ? Theme.focus : Theme.outline
    activeFocusOnTab: true
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    Text { id: label; anchors.centerIn: parent; text: button.text; color: Theme.foreground; font.pixelSize: 12 }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: button.clicked() }
}
