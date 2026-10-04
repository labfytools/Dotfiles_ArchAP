import QtQuick
import Quickshell
import "../components"

Rectangle {
    id: card
    required property var notification
    required property var service
    readonly property var live: service.live(notification.internalId)
    readonly property string iconSource: {
        const icon = notification.appIcon || "";
        if (icon.startsWith("/")) return "file://" + icon;
        if (icon.startsWith("file://") || icon.startsWith("data:")) return icon;
        if (icon) return Quickshell.iconPath(icon, true);
        const entry = notification.desktopEntry
            ? DesktopEntries.heuristicLookup(notification.desktopEntry) : null;
        return entry && entry.icon ? Quickshell.iconPath(entry.icon, true) : "";
    }
    implicitHeight: bodyText.visible || image.visible || actions.visible ? 95 + image.height + actions.height : 64
    height: implicitHeight
    radius: 4
    color: "#313244"
    Column {
        anchors.fill: parent; anchors.margins: 10; spacing: 4
        Row {
            width: parent.width; height: 16; spacing: 7
            Item {
                width: 14; height: 14
                Image { id: appIcon; anchors.fill: parent; source: card.iconSource; fillMode: Image.PreserveAspectFit; visible: status === Image.Ready }
                NerdIcon { anchors.centerIn: parent; visible: !appIcon.visible; text: ""; color: "#cba6f7"; font.pixelSize: 13 }
            }
            Text {
                width: parent.width - 48
                text: card.notification.appName || card.notification.desktopEntry || "Notification"
                textFormat: Text.PlainText; color: "#a6adc8"; font.pixelSize: 11; elide: Text.ElideRight
            }
            Text { visible: !!card.live; text: "●"; color: "#a6e3a1"; font.pixelSize: 10 }
            NerdIcon {
                text: ""; color: closePointer.containsMouse ? "#f38ba8" : "#a6adc8"; font.pixelSize: 12
                MouseArea { id: closePointer; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true; onClicked: card.service.dismiss(card.notification.internalId) }
            }
        }
        Text { width: parent.width; text: card.notification.summary; textFormat: Text.PlainText; color: "#cdd6f4"; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight }
        Text { id: bodyText; width: parent.width; visible: text.length > 0; text: card.notification.body || ""; textFormat: Text.PlainText; color: "#bac2de"; font.pixelSize: 11; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight }
        Image { id: image; width: parent.width; height: status === Image.Ready ? Math.min(110, implicitHeight) : 0; visible: status === Image.Ready; source: card.notification.image || ""; fillMode: Image.PreserveAspectFit }
        Flow {
            id: actions
            width: parent.width
            visible: !!card.live && card.live.actions.length > 0
            height: visible ? 26 : 0
            spacing: 5
            Repeater {
                model: card.live ? card.live.actions : []
                delegate: Rectangle {
                    required property var modelData
                    width: label.implicitWidth + 16; height: 24; radius: 4; color: "#45475a"
                    Text { id: label; anchors.centerIn: parent; text: modelData.text; textFormat: Text.PlainText; color: "#cdd6f4"; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; onClicked: modelData.invoke() }
                }
            }
        }
    }
}
