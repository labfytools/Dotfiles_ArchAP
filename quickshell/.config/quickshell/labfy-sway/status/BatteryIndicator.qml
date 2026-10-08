import QtQuick
import Quickshell.Io
import Quickshell.Services.UPower
import "../components"
import "../theme"
import "StatusColorRoles.js" as StatusColorRoles

Item {
    id: indicator
    signal activated()
    function refreshThreshold() { thresholdFile.reload() }
    readonly property var battery: UPower.displayDevice
    readonly property bool available: battery && battery.ready && battery.isPresent
    readonly property int percent: available ? Math.round(battery.percentage * 100) : 0
    readonly property bool charging: available && battery.state === UPowerDeviceState.Charging
    readonly property bool full: available && battery.state === UPowerDeviceState.FullyCharged
    readonly property string stateLabel: !available ? "Indisponible"
        : charging ? "En charge"
        : full ? "Pleine"
        : battery.state === UPowerDeviceState.PendingCharge ? "En attente de charge"
        : battery.state === UPowerDeviceState.PendingDischarge ? "En attente de décharge"
        : battery.state === UPowerDeviceState.Discharging ? "Décharge"
        : battery.state === UPowerDeviceState.Empty ? "Vide" : "État inconnu"
    readonly property real remaining: !available ? 0
        : charging ? battery.timeToFull
        : battery.state === UPowerDeviceState.Discharging ? battery.timeToEmpty : 0
    readonly property int configuredThreshold: {
        const raw = thresholdFile.text().trim();
        return /^[0-9]{1,3}$/.test(raw) ? Number(raw) : -1;
    }
    readonly property string detail: !available ? "Batterie indisponible"
        : "Batterie : " + percent + " %\n" + stateLabel
            + (remaining > 0 ? "\n" + (charging ? "Charge complète dans : " : "Temps restant : ")
                + Math.floor(remaining / 3600) + " h " + String(Math.floor(remaining % 3600 / 60)).padStart(2, "0") : "")
            + (battery.healthSupported ? "\nSanté : " + Math.round(battery.healthPercentage * 100) + " %" : "")
            + (configuredThreshold >= 0 ? "\nLimite configurée : " + configuredThreshold + " %" : "")
    width: content.width
    height: 26

    FileView {
        id: thresholdFile
        path: "/sys/class/power_supply/BAT1/charge_control_end_threshold"
        watchChanges: true
        onFileChanged: reload()
    }

    Rectangle { anchors.fill: parent; radius: 4; color: pointer.containsMouse ? Theme.border : "transparent" }
    PercentIndicatorContent {
        id: content
        // Les seuils 30/15 % sont visuels ; ils ne modifient aucune politique UPower.
        glyph: !indicator.available ? "󰂑"
            : indicator.charging ? "󰂄"
            : indicator.full ? "󰁹"
            : indicator.percent <= 15 ? "󰁺"
            : indicator.percent <= 30 ? "󰁻"
            : indicator.percent <= 50 ? "󰁽"
            : indicator.percent <= 75 ? "󰁿" : "󰁹"
        available: indicator.available
        percent: indicator.percent
        tint: Theme[StatusColorRoles.battery(indicator.available, indicator.percent)]
        valueTint: Theme[StatusColorRoles.batteryValue(indicator.available, indicator.percent)]
        glyphPixelSize: 18
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onContainsMouseChanged: if (containsMouse) indicator.refreshThreshold()
        onClicked: indicator.activated()
    }
    StatusTooltip { target: indicator; hovered: pointer.containsMouse; message: indicator.detail }
}
