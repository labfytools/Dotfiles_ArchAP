import QtQuick
import "../theme"

Item {
    id: page
    signal backRequested()
    readonly property bool busy: AppearanceController.appearanceBusy || AppearanceController.nightLightBusy
    readonly property var names: ({ frappe: "Frappé", macchiato: "Macchiato", mocha: "Mocha" })

    Column {
        anchors.fill: parent
        spacing: 13
        Row {
            spacing: 8; height: 30
            ActionButton { label: ""; onClicked: page.backRequested() }
            Text { text: "Mode Soleil"; color: Theme.foreground; font.pixelSize: 16; font.bold: true; height: 30; verticalAlignment: Text.AlignVCenter }
        }
        Text { text: "PROFIL HAUTE VISIBILITÉ"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Row {
            spacing: 8
            Repeater {
                model: [ { key: false, label: "Désactivé" }, { key: true, label: "Activé" } ]
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool selected: AppearanceController.sunMode === modelData.key
                    width: (page.width - 8) / 2; height: 43; radius: 4
                    color: selected ? Theme.selectedBackground : Theme.buttonBackground
                    border.width: selected ? 2 : 1; border.color: selected ? Theme.accent : Theme.border
                    Text { anchors.centerIn: parent; text: modelData.label; color: parent.selected ? Theme.selectedForeground : Theme.foreground; font.pixelSize: 12 }
                    MouseArea { anchors.fill: parent; enabled: !page.busy && !parent.selected; onClicked: AppearanceController.setSunMode(modelData.key) }
                }
            }
        }
        Text { text: "STYLE"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Row {
            spacing: 8
            Repeater {
                model: [ { key: "light", label: "Clair" }, { key: "dark", label: "Sombre" } ]
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool selected: AppearanceController.sunVariant === modelData.key
                    width: (page.width - 8) / 2; height: 43; radius: 4
                    color: selected ? Theme.selectedBackground : Theme.buttonBackground
                    border.width: selected ? 2 : 1; border.color: selected ? Theme.accent : Theme.border
                    Text { anchors.centerIn: parent; text: modelData.label; color: parent.selected ? Theme.selectedForeground : Theme.foreground; font.pixelSize: 12 }
                    MouseArea { anchors.fill: parent; enabled: !page.busy && !parent.selected; onClicked: AppearanceController.setSunVariant(modelData.key) }
                }
            }
        }
        Text { visible: AppearanceController.sunVariant === "dark"; text: "FLAVOR SOMBRE"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Row {
            visible: AppearanceController.sunVariant === "dark"
            spacing: 6
            Repeater {
                model: ["frappe", "macchiato", "mocha"]
                delegate: Rectangle {
                    required property string modelData
                    readonly property bool selected: AppearanceController.sunDarkFlavor === modelData
                    width: (page.width - 12) / 3; height: 40; radius: 4
                    color: selected ? Theme.selectedBackground : Theme.buttonBackground
                    border.width: selected ? 2 : 1; border.color: selected ? Theme.accent : Theme.border
                    Text { anchors.centerIn: parent; text: page.names[modelData]; color: parent.selected ? Theme.selectedForeground : Theme.foreground; font.pixelSize: 11 }
                    MouseArea { anchors.fill: parent; enabled: !page.busy && !parent.selected; onClicked: AppearanceController.setSunDarkFlavor(modelData) }
                }
            }
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: AppearanceController.sunVariant === "light" ? "Latte · contraste renforcé" : page.names[AppearanceController.sunDarkFlavor] + " · contraste renforcé"
            color: Theme.foreground; font.pixelSize: 12
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: "La lumière nocturne est temporairement suspendue pendant le Mode Soleil."
            color: Theme.secondaryForeground; font.pixelSize: 11
        }
        Text {
            visible: page.busy || !!AppearanceController.appearanceError
            width: parent.width; wrapMode: Text.Wrap
            text: page.busy ? "Application…" : AppearanceController.appearanceError
            color: AppearanceController.appearanceError ? Theme.warningForeground : Theme.secondaryForeground; font.pixelSize: 11
        }
    }
}
