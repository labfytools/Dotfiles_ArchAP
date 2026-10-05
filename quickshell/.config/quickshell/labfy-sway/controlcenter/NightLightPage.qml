import QtQuick
import QtQuick.Controls
import "../theme"

Item {
    id: page
    signal backRequested()
    property int draftTemperature: AppearanceController.nightTemperature
    readonly property bool busy: AppearanceController.nightLightBusy || AppearanceController.appearanceBusy
    Connections {
        target: AppearanceController
        function onNightTemperatureChanged() { page.draftTemperature = AppearanceController.nightTemperature; }
    }
    Column {
        anchors.fill: parent
        spacing: 14
        Row {
            spacing: 8; height: 30
            ActionButton { label: ""; onClicked: page.backRequested() }
            Text { text: "Lumière nocturne"; color: Theme.foreground; font.pixelSize: 16; font.bold: true; height: 30; verticalAlignment: Text.AlignVCenter }
        }
        Text { text: "MODE"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Row {
            spacing: 8
            Repeater {
                model: [
                    { key: "off", label: "Désactivée" },
                    { key: "auto", label: "Auto" },
                    { key: "on", label: "Activée" }
                ]
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool selected: AppearanceController.nightLightMode === modelData.key
                    width: (page.width - 16) / 3; height: 44; radius: 4
                    color: selected ? Theme.selectedBackground : Theme.buttonBackground
                    border.width: selected ? 2 : 1
                    border.color: selected ? Theme.accent : Theme.border
                    opacity: page.busy ? 0.6 : 1
                    Text { anchors.centerIn: parent; text: modelData.label; color: parent.selected ? Theme.selectedForeground : Theme.foreground; font.pixelSize: 11; font.bold: parent.selected }
                    MouseArea { anchors.fill: parent; enabled: !page.busy && !parent.selected; onClicked: AppearanceController.setNightLightMode(modelData.key) }
                }
            }
        }
        Text {
            width: parent.width
            text: AppearanceController.nightLightMode === "auto" ? "Lever et coucher du soleil"
                : AppearanceController.nightLightMode === "on" ? AppearanceController.nightTemperature + " K en permanence"
                : "Couleurs neutres"
            color: Theme.secondaryForeground; font.pixelSize: 12
        }
        Text {
            visible: AppearanceController.nightLightSuspended
            width: parent.width; wrapMode: Text.Wrap
            text: "Préférence : " + (AppearanceController.nightLightMode === "auto" ? "Auto" : AppearanceController.nightLightMode === "on" ? "Activée" : "Désactivée") + " · État : temporairement suspendue par le Mode Soleil"
            color: Theme.foreground; font.pixelSize: 12
        }
        Text { text: "TEMPÉRATURE DE NUIT"; color: Theme.accentForeground; font.pixelSize: 11; font.bold: true }
        Row {
            width: parent.width; spacing: 10
            Slider {
                id: nightSlider
                width: parent.width - 74
                from: 2500; to: 5000; stepSize: 100
                value: page.draftTemperature
                enabled: !page.busy
                onMoved: page.draftTemperature = Math.round(value / 100) * 100
            }
            Text { text: page.draftTemperature + " K"; color: Theme.foreground; font.pixelSize: 12; width: 64; verticalAlignment: Text.AlignVCenter; height: nightSlider.height }
        }
        ActionButton {
            label: "Appliquer"
            enabled: !page.busy && page.draftTemperature !== AppearanceController.nightTemperature
            onClicked: AppearanceController.setNightTemperature(page.draftTemperature)
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: AppearanceController.nightScheduleConfigured ? "Planification automatique · Position locale configurée" : "Planification à configurer"
            color: Theme.secondaryForeground; font.pixelSize: 11
        }
        Text {
            visible: page.busy || !!AppearanceController.nightLightError
            width: parent.width; wrapMode: Text.Wrap
            text: page.busy ? "Application…" : AppearanceController.nightLightError
            color: AppearanceController.nightLightError ? Theme.warningForeground : Theme.secondaryForeground
            font.pixelSize: 11
        }
    }
}
