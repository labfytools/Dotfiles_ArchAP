import QtQuick
import "../theme"

Item {
    id: page
    signal backRequested()
    readonly property var options: [
        { key: "latte", name: "Latte", description: "Clair" },
        { key: "frappe", name: "Frappé", description: "Sombre doux" },
        { key: "macchiato", name: "Macchiato", description: "Sombre" },
        { key: "mocha", name: "Mocha", description: "Sombre profond" }
    ]
    readonly property var names: ({ latte: "Latte", frappe: "Frappé", macchiato: "Macchiato", mocha: "Mocha" })
    readonly property bool busy: AppearanceController.appearanceBusy

    Column {
        anchors.fill: parent
        spacing: 10
        Row {
            spacing: 8; height: 30
            ActionButton { label: ""; onClicked: page.backRequested() }
            Text { text: "Thème"; color: Theme.foreground; font.pixelSize: 16; font.bold: true; height: 30; verticalAlignment: Text.AlignVCenter }
        }
        Text { text: "MODE"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Row {
            spacing: 8
            Repeater {
                model: [
                    { key: "manual", name: "Manuel" },
                    { key: "wallpaper", name: "Selon le fond" }
                ]
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool active: AppearanceController.themeMode === modelData.key
                    width: (page.width - 8) / 2; height: 44; radius: 4
                    color: active ? Theme.selectedBackground : Theme.buttonBackground
                    border.width: active ? 2 : 1
                    border.color: active ? Theme.accent : Theme.border
                    opacity: page.busy ? 0.6 : 1
                    Text { anchors.centerIn: parent; text: modelData.name; color: parent.active ? Theme.selectedForeground : Theme.foreground; font.pixelSize: 12; font.bold: parent.active }
                    MouseArea { anchors.fill: parent; enabled: !page.busy && !parent.active; onClicked: AppearanceController.setThemeMode(modelData.key) }
                }
            }
        }
        Text {
            width: parent.width
            text: "Thème effectif : " + (page.names[AppearanceController.effectiveFlavor] || "Mocha")
            color: Theme.foreground; font.pixelSize: 12
        }
        Text {
            visible: AppearanceController.themeMode === "wallpaper"
            width: parent.width; wrapMode: Text.Wrap
            text: "Le thème suit le fond appliqué. Choix manuel conservé : "
                  + (page.names[AppearanceController.manualFlavor] || "Mocha") + "."
            color: Theme.secondaryForeground; font.pixelSize: 11
        }
        Text {
            visible: AppearanceController.themeMode === "manual"
            text: "FLAVOR MANUEL"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true
        }
        Grid {
            visible: AppearanceController.themeMode === "manual"
            columns: 2; spacing: 8
            Repeater {
                model: page.options
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool active: AppearanceController.manualFlavor === modelData.key
                    width: (page.width - 8) / 2; height: 58; radius: 4
                    color: active ? Theme.buttonHover : Theme.buttonBackground
                    border.width: active ? 2 : 1
                    border.color: active ? Theme.accent : Theme.border
                    opacity: page.busy ? 0.6 : 1
                    Column {
                        anchors.centerIn: parent; spacing: 3
                        Text { text: modelData.name + (parent.parent.active ? "  ✓" : ""); color: Theme.foreground; font.pixelSize: 13; font.bold: true }
                        Text { text: modelData.description; color: Theme.secondaryForeground; font.pixelSize: 10 }
                    }
                    MouseArea { anchors.fill: parent; enabled: !page.busy && !parent.active; onClicked: AppearanceController.setManualFlavor(modelData.key) }
                }
            }
        }
        Text {
            visible: page.busy || !!AppearanceController.appearanceError
            width: parent.width; wrapMode: Text.Wrap
            text: page.busy ? "Application…" : AppearanceController.appearanceError
            color: AppearanceController.appearanceError ? Theme.warningForeground : Theme.secondaryForeground
            font.pixelSize: 11
        }
    }
}
