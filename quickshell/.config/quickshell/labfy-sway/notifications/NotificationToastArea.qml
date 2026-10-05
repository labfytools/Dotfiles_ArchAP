import QtQuick
import Quickshell

PopupWindow {
    id: area
    required property var barWindow
    required property var service
    anchor.window: barWindow
    anchor.rect.x: barWindow.width - implicitWidth - 8
    anchor.rect.y: barWindow.height + 8
    anchor.edges: Edges.Top | Edges.Left
    anchor.gravity: Edges.Bottom | Edges.Right
    implicitWidth: 386
    // WHY: redimensionner un popup Wayland déjà visible peut présenter un
    // ancien buffer étiré pendant que Qt recalcule les cartes. La surface
    // garde sa taille ; seule la pile interne suit les notifications.
    // INVARIANT: hauteur native indépendante des arrivées et expirations.
    implicitHeight: 550
    visible: service.toasts.length > 0
    grabFocus: false
    color: "transparent"
    // CONTRACT: la partie transparente ne capte pas les clics du bureau.
    mask: Region { item: viewport }
    Flickable {
        id: viewport
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        height: Math.min(area.height - 16, contentHeight)
        contentWidth: width
        contentHeight: stack.childrenRect.height
        clip: true
        interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: stack
            width: viewport.width
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
}
