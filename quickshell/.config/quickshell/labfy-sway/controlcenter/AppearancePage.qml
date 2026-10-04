import QtQuick
import "../components"
import "../theme"

Item {
    id: page
    signal backRequested()
    signal wallpaperRequested()

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
                Text { text: "Galerie locale et choix explicite"; color: Theme.secondaryForeground; font.pixelSize: 11 }
            }
            MouseArea { id: pointer; anchors.fill: parent; hoverEnabled: true; onClicked: page.wallpaperRequested() }
        }
        Rectangle {
            width: parent.width; height: 58; radius: 4; color: Theme.buttonBackground
            Text {
                anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                text: "Thème  •  " + AppearanceController.effectiveFlavor + " / " + AppearanceController.effectiveAccent
                color: Theme.foreground; font.pixelSize: 12
            }
        }
    }
}
