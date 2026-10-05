import QtQuick
import "../components"
import "../theme"

Item {
    id: page
    signal backRequested()
    signal wallpaperRequested()
    signal themeRequested()
    readonly property var flavorNames: ({ latte: "Latte", frappe: "Frappé", macchiato: "Macchiato", mocha: "Mocha" })

    Column {
        anchors.fill: parent
        spacing: 14
        Row {
            spacing: 10
            ActionButton { label: ""; onClicked: page.backRequested() }
            Text { text: "Apparence"; color: Theme.foreground; font.pixelSize: 16; font.bold: true; height: 30; verticalAlignment: Text.AlignVCenter }
        }
        Rectangle {
            width: parent.width; height: 72; radius: 4
            color: pointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
            NerdIcon { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "󰸉"; color: Theme.accent; font.pixelSize: 22 }
            Column {
                anchors.left: parent.left; anchors.leftMargin: 47; anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Text { text: "Fond d'écran"; color: Theme.foreground; font.pixelSize: 14; font.bold: true }
                Text { text: AppearanceController.effectiveWallpaper.split("/").pop(); color: Theme.secondaryForeground; font.pixelSize: 11; width: 290; elide: Text.ElideMiddle }
            }
            MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: page.wallpaperRequested() }
        }
        Rectangle {
            width: parent.width; height: 72; radius: 4
            color: themePointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
            NerdIcon { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "󰏘"; color: Theme.accent; font.pixelSize: 22 }
            Column {
                anchors.left: parent.left; anchors.leftMargin: 47; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                Text { text: "Thème"; color: Theme.foreground; font.pixelSize: 14; font.bold: true }
                Text {
                    text: (page.flavorNames[AppearanceController.effectiveFlavor] || "Mocha")
                          + " · " + (AppearanceController.themeMode === "wallpaper" ? "Selon le fond" : "Manuel")
                    color: Theme.secondaryForeground; font.pixelSize: 11
                }
            }
            MouseArea { id: themePointer; anchors.fill: parent; hoverEnabled: true; onClicked: page.themeRequested() }
        }
    }
}
