import QtQuick
import Quickshell
import "../notifications"

Rectangle {
    id: clockCapsule
    property bool open: false
    required property int unreadCount
    required property int criticalUnreadCount
    signal toggled()
    // INVARIANT: la largeur fixe garde le texte sur le centre de l'écran, même avec "9+".
    width: 184
    height: 26
    radius: 4
    color: open ? "#cba6f7" : pointer.containsMouse ? "#45475a" : "#313244"
    Accessible.role: Accessible.Button
    Accessible.name: unreadCount === 0 ? "Date et heure"
        : "Date et heure, " + unreadCount + (unreadCount === 1
            ? " notification non lue" : " notifications non lues")

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    Text {
        id: clockText
        // CONTRACT: le centre du texte coïncide avec celui de la barre, sans dépendre du badge.
        anchors.centerIn: parent
        text: Qt.formatDateTime(clock.date, "dd/MM HH:mm")
        color: clockCapsule.open ? "#1e1e2e" : "#cdd6f4"
        font.pixelSize: 13
        font.weight: Font.Bold
    }

    UnreadIndicator {
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        unreadCount: clockCapsule.unreadCount
        criticalUnreadCount: clockCapsule.criticalUnreadCount
        inverted: clockCapsule.open
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onClicked: clockCapsule.toggled()
    }

    PopupWindow {
        anchor.item: clockCapsule
        anchor.edges: Edges.Bottom | Edges.Left
        anchor.gravity: Edges.Bottom | Edges.Right
        anchor.margins.bottom: -6
        visible: pointer.containsMouse
        grabFocus: false
        color: "transparent"
        implicitWidth: tooltipText.implicitWidth + 16
        implicitHeight: 26
        Rectangle {
            anchors.fill: parent
            radius: 4
            color: "#313244"
            border.color: "#45475a"
            Text {
                id: tooltipText
                anchors.centerIn: parent
                text: clockCapsule.unreadCount === 0 ? "Date et notifications"
                    : clockCapsule.unreadCount + (clockCapsule.unreadCount === 1
                        ? " notification non lue" : " notifications non lues")
                color: "#cdd6f4"
                font.pixelSize: 11
            }
        }
    }
}
