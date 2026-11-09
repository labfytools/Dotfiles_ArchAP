import QtQuick
import QtQuick.Controls
import "../components"
import "../theme"
import "../rgbkeyboard"

Item {
    id: page
    property bool activePage: false
    property string selectedColor: "#8000FF"
    property int selectedPercent: 100
    signal backRequested()
    onActivePageChanged: if (activePage && !RgbKeyboardService.busy) RgbKeyboardService.refresh()
    Column {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        spacing: 10
        Item {
            width: parent.width; height: 28
            NerdIcon { id: back; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "" }
            Text { anchors.left: back.right; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                text: "Clavier RGB"; color: Theme.foreground; font.pixelSize: 16; font.bold: true }
            MouseArea { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: 180; onClicked: page.backRequested() }
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap; font.pixelSize: 12
            color: RgbKeyboardService.available ? Theme.successForeground : Theme.warningForeground
            text: RgbKeyboardService.busy ? "Commande en cours…" : RgbKeyboardService.available ? "ITE5570 · " + RgbKeyboardService.device : "Contrôleur indisponible"
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap; font.pixelSize: 12; color: Theme.secondaryForeground
            text: "Dernière commande : " + (RgbKeyboardService.commandedMode === "software" ? "mode logiciel" : RgbKeyboardService.commandedMode === "firmware" ? "mode ASUS" : "inconnue")
                + (RgbKeyboardService.lastColor ? " · " + RgbKeyboardService.lastColor + " · " + RgbKeyboardService.lastPercent + " %" : "")
                + "\nHistorique local ; couleur et mode physiques non mesurés."
        }
        Grid {
            width: parent.width; columns: 4; spacing: 6
            Repeater {
                model: RgbKeyboardService.palette
                delegate: Rectangle {
                    id: swatch
                    required property var modelData
                    width: (page.width - 18) / 4; height: 42; radius: 4
                    color: pointer.containsMouse ? Theme.buttonHover : Theme.buttonBackground
                    border.width: page.selectedColor.toUpperCase() === modelData.color ? 1 : 0
                    border.color: Theme.lavender
                    Rectangle { width: 12; height: 12; radius: 4; color: swatch.modelData.color; anchors.horizontalCenter: parent.horizontalCenter; y: 5 }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; y: 22; text: swatch.modelData.name; font.pixelSize: 10; color: Theme.foreground }
                    MouseArea {
                        id: pointer
                        objectName: "rgbPreset-" + swatch.modelData.name
                        anchors.fill: parent; hoverEnabled: true
                        enabled: !RgbKeyboardService.busy && RgbKeyboardService.available
                        onClicked: {
                            if (RgbKeyboardService.preset(swatch.modelData.color)) {
                                page.selectedColor = swatch.modelData.color;
                                page.selectedPercent = 100;
                            }
                        }
                    }
                }
            }
        }
        Row {
            width: parent.width; spacing: 8
            Rectangle { width: 30; height: 30; radius: 4; color: RgbKeyboardService.validColor(page.selectedColor) ? page.selectedColor : Theme.buttonBackground }
            TextField {
                width: parent.width - 38; height: 30; maximumLength: 7
                text: page.selectedColor; placeholderText: "#RRGGBB"; color: Theme.foreground
                font.pixelSize: 12; selectByMouse: true; enabled: !RgbKeyboardService.busy
                onTextEdited: page.selectedColor = text
                background: Rectangle { radius: 4; color: Theme.inputBackground; border.color: RgbKeyboardService.validColor(page.selectedColor) ? Theme.inputBorder : Theme.danger }
            }
        }
        Text { text: "Intensité HID : " + page.selectedPercent + " %"; color: Theme.foreground; font.pixelSize: 12 }
        Slider {
            id: intensity; width: parent.width; height: 26; from: 0; to: 100; stepSize: 1
            value: page.selectedPercent; enabled: !RgbKeyboardService.busy
            // CONTRACT: dragging only updates the draft; no Process until Apply.
            onMoved: page.selectedPercent = Math.round(value)
            background: Rectangle { x: intensity.leftPadding; y: intensity.topPadding + intensity.availableHeight / 2 - height / 2
                width: intensity.availableWidth; height: 6; radius: 3; color: Theme.buttonBackground
                Rectangle { width: intensity.visualPosition * parent.width; height: parent.height; radius: 3; color: Theme.lavender } }
            handle: Rectangle { x: intensity.leftPadding + intensity.visualPosition * (intensity.availableWidth - width)
                y: intensity.topPadding + intensity.availableHeight / 2 - height / 2; width: 12; height: 16; radius: 3; color: Theme.lavender }
        }
        Row {
            spacing: 6
            ActionButton { label: "Appliquer"; enabled: !RgbKeyboardService.busy && RgbKeyboardService.available && RgbKeyboardService.validColor(page.selectedColor)
                onClicked: RgbKeyboardService.applyColor(page.selectedColor, page.selectedPercent) }
            ActionButton { label: "Intensité"; enabled: !RgbKeyboardService.busy && RgbKeyboardService.available && !!RgbKeyboardService.lastColor
                onClicked: RgbKeyboardService.intensity(page.selectedPercent) }
            ActionButton { label: "Éteindre"; enabled: !RgbKeyboardService.busy && RgbKeyboardService.available; onClicked: RgbKeyboardService.off() }
        }
        Row {
            spacing: 6
            // Restoration stays enabled on a failed/stale status; CLI rechecks identity.
            ActionButton { objectName: "rgbFirmware"; label: "Mode ASUS"; enabled: !RgbKeyboardService.busy; onClicked: RgbKeyboardService.firmware() }
            ActionButton { label: "Actualiser"; enabled: !RgbKeyboardService.busy; onClicked: RgbKeyboardService.refresh() }
        }
        CheckBox {
            text: "Restaurer ma couleur au démarrage"; checked: RgbKeyboardService.restoreEnabled
            enabled: !RgbKeyboardService.busy
            onToggled: RgbKeyboardService.setRestoreEnabled(checked)
            contentItem: Text { text: parent.text; color: Theme.foreground; font.pixelSize: 11; leftPadding: 28; verticalAlignment: Text.AlignVCenter }
            indicator: Rectangle { width: 16; height: 16; radius: 3; anchors.verticalCenter: parent.verticalCenter; color: Theme.buttonBackground; border.color: Theme.outline
                Rectangle { anchors.fill: parent; anchors.margins: 4; radius: 1; color: Theme.lavender; visible: RgbKeyboardService.restoreEnabled } }
        }
        Text { width: parent.width; wrapMode: Text.Wrap; text: "Désactivé par défaut. Mode ASUS empêche la restauration. Aucun réglage WMI modifié."
            color: Theme.secondaryForeground; font.pixelSize: 10 }
        Text { width: parent.width; wrapMode: Text.Wrap; text: RgbKeyboardService.message; color: Theme.secondaryForeground; font.pixelSize: 11 }
    }
}
