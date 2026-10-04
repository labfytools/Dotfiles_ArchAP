import QtQuick
import Quickshell
import Quickshell.Services.Notifications
import "../components"
import "../theme"

Rectangle {
    id: card
    required property var entry
    required property var service
    readonly property var notification: entry.notification
    readonly property string iconSource: {
        const icon = notification.appIcon || "";
        if (icon.startsWith("/")) return "file://" + icon;
        if (icon.startsWith("file://") || icon.startsWith("data:")) return icon;
        if (icon) return Quickshell.iconPath(icon, true);
        const desktop = notification.desktopEntry ? DesktopEntries.heuristicLookup(notification.desktopEntry) : null;
        return desktop && desktop.icon ? Quickshell.iconPath(desktop.icon, true) : "";
    }
    readonly property int serverTimeout: notification.urgency === NotificationUrgency.Low ? 4000
        : notification.urgency === NotificationUrgency.Critical ? 0 : 6000
    readonly property int timeout: notification.expireTimeout < 0 ? serverTimeout
        : notification.expireTimeout
    width: 370
    implicitHeight: content.implicitHeight + 20
    radius: 4
    color: Theme.popupBackground
    border.color: notification.urgency === NotificationUrgency.Critical ? Theme.danger : Theme.border
    // CONTRACT: 0 interdit l'expiration automatique. Les durées sont en ms.
    Timer {
        interval: Math.max(1, card.timeout)
        running: card.timeout > 0
        onTriggered: card.service.expire(card.entry.internalId)
    }
    Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 5
        Row {
            width: parent.width
            spacing: 7
            Item {
                width: 18; height: 18
                Image {
                    id: icon
                    anchors.fill: parent
                    source: card.iconSource
                    fillMode: Image.PreserveAspectFit
                    visible: status === Image.Ready
                }
                NerdIcon { anchors.centerIn: parent; visible: !icon.visible; text: ""; color: Theme.accent }
            }
            Text {
                width: parent.width - 48
                text: card.notification.appName || "Notification"
                textFormat: Text.PlainText
                color: Theme.secondaryForeground
                font.pixelSize: 11
                elide: Text.ElideRight
            }
            NerdIcon {
                text: ""; color: Theme.secondaryForeground
                MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: card.service.dismiss(card.entry.internalId) }
            }
        }
        Text { width: parent.width; text: card.notification.summary; textFormat: Text.PlainText; color: Theme.foreground; font.bold: true; wrapMode: Text.Wrap; maximumLineCount: 2 }
        Text { width: parent.width; visible: text.length > 0; text: card.notification.body; textFormat: Text.PlainText; color: Theme.subtext1; font.pixelSize: 12; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
        Image {
            width: parent.width; height: status === Image.Ready ? Math.min(120, implicitHeight) : 0
            visible: status === Image.Ready
            source: card.notification.image || ""
            fillMode: Image.PreserveAspectFit
        }
        Flow {
            width: parent.width
            spacing: 5
            Repeater {
                model: card.notification.actions
                delegate: Rectangle {
                    required property var modelData
                    width: actionLabel.implicitWidth + 16; height: 25; radius: 4; color: Theme.border
                    Text { id: actionLabel; anchors.centerIn: parent; text: modelData.text; textFormat: Text.PlainText; color: Theme.foreground; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; onClicked: modelData.invoke() }
                }
            }
        }
    }
}
