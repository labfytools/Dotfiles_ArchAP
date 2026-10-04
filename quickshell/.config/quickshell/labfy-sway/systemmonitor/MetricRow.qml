import QtQuick
import "../theme"

Column {
    id: row
    required property string label
    required property string value
    required property real percentage
    property color accent: Theme.mauve
    width: parent.width
    spacing: 6

    Row {
        width: parent.width
        Text { id: labelText; text: row.label; color: Theme.foreground; font.pixelSize: 12 }
        Item { width: Math.max(0, parent.width - valueText.width - labelText.width); height: 1 }
        Text { id: valueText; text: row.value; color: Theme.subtext1; font.pixelSize: 12 }
    }
    Rectangle {
        width: parent.width
        height: 5
        radius: 3
        color: Theme.buttonBackground
        Rectangle {
            width: parent.width * Math.max(0, Math.min(100, row.percentage)) / 100
            height: parent.height
            radius: 3
            color: row.accent
        }
    }
}
