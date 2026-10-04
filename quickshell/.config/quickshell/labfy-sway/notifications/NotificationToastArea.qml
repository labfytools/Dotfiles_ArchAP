import QtQuick
import Quickshell

PopupWindow {
    id: area
    required property var barWindow
    required property var service
    property bool monitorOpen: false
    property int monitorWidth: 400
    anchor.window: barWindow
    // Laisser les notifications visibles sans recouvrir le moniteur ouvert.
    anchor.rect.x: monitorOpen ? barWindow.width - monitorWidth - implicitWidth - 16
        : barWindow.width - implicitWidth - 8
    anchor.rect.y: barWindow.height + 8
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    implicitWidth: 386
    implicitHeight: Math.min(550, stack.implicitHeight + 16)
    visible: service.toasts.length > 0
    grabFocus: false
    color: "transparent"
    Column {
        id: stack
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 7
        Repeater {
            model: area.service.toasts.slice(-4).reverse()
            delegate: NotificationToast {
                required property var modelData
                entry: modelData
                service: area.service
                width: stack.width
            }
        }
    }
}
