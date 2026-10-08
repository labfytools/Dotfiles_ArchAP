import QtQuick
import Quickshell
import Quickshell.Services.SystemTray
import Quickshell.Widgets
import "../theme"

Item {
    id: entry
    required property var item
    required property var barWindow
    width: 26
    height: 26
    readonly property string detail: {
        const heading = item.tooltipTitle || item.title || "Application";
        return heading + (item.tooltipDescription ? "\n" + item.tooltipDescription : "");
    }

    Rectangle { anchors.fill: parent; radius: 4; color: pointer.containsMouse ? Theme.border : "transparent" }
    IconImage {
        anchors.centerIn: parent
        // CONTRACT: l'image fournie par l'application reste inchangée ; seul
        // son emplacement dans le slot de 26 px est harmonisé.
        width: 20
        height: 20
        source: entry.item.icon
        opacity: entry.item.status === Status.Passive ? 0.7 : 1
    }
    Rectangle {
        visible: entry.item.status === Status.NeedsAttention
        width: 4; height: 4; radius: 2
        color: Theme.accent
        anchors.right: parent.right
        anchors.top: parent.top
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
        onClicked: mouse => {
            if (mouse.button === Qt.MiddleButton) entry.item.secondaryActivate();
            else if (mouse.button === Qt.RightButton && entry.item.hasMenu) menuAnchor.open();
            else if (mouse.button === Qt.LeftButton) {
                if (entry.item.onlyMenu && entry.item.hasMenu) menuAnchor.open();
                else entry.item.activate();
            }
        }
        onWheel: wheel => entry.item.scroll(wheel.angleDelta.y, false)
    }
    QsMenuAnchor {
        id: menuAnchor
        menu: entry.item.menu
        anchor.item: entry
        anchor.margins.bottom: -5
        anchor.edges: Edges.Top | Edges.Left
        anchor.gravity: Edges.Bottom | Edges.Right
    }
    StatusTooltip { target: entry; hovered: pointer.containsMouse; message: entry.detail }
}
