import QtQuick
import "../controlcenter"
import "../theme"
import "StatusColorRoles.js" as StatusColorRoles

Row {
    id: area
    required property var barWindow
    required property var wifiDevice
    required property var adapter
    required property bool controlCenterOpen
    required property bool clipboardOpen
    required property var audioBrightnessController
    signal openPageRequested(int page)
    signal toggleControlCenterRequested()
    signal toggleRemovableMediaRequested()
    signal toggleClipboardRequested()
    function refreshBatteryThreshold() { batteryIndicator.refreshThreshold() }
    function closeRemovableMedia() { removableMediaIndicator.popupOpen = false }
    function setRemovableMediaOpen(open) { removableMediaIndicator.popupOpen = open }
    readonly property bool removableMediaOpen: removableMediaIndicator.popupOpen
    // INVARIANT: huit pixels de part et d'autre des deux séparateurs identiques.
    spacing: 8
    height: 26

    // CONTRACT: statuts, actions, puis tray en dernier ; callbacks inchangés.
    Row {
        spacing: 6
        height: 26
        NetworkIndicator { wifiDevice: area.wifiDevice; onActivated: area.openPageRequested(1) }
        BluetoothIndicator { adapter: area.adapter; onActivated: area.openPageRequested(2) }
        BatteryIndicator { id: batteryIndicator; onActivated: area.openPageRequested(5) }
        ScrollIcon {
            glyph: area.audioBrightnessController.volumeMuted ? "󰝟" : "󰕾"
            glyphColor: Theme[StatusColorRoles.volume(
                area.audioBrightnessController.volumeAvailable,
                area.audioBrightnessController.volumeMuted)]
            glyphPixelSize: 28
            label: "Volume"
            percent: area.audioBrightnessController.volumePercent
            available: area.audioBrightnessController.volumeAvailable
            onAdjusted: steps => area.audioBrightnessController.adjustVolume(steps)
        }
        ScrollIcon {
            glyph: "󰖨"
            glyphColor: Theme.yellow
            glyphPixelSize: 26
            label: "Luminosité"
            percent: area.audioBrightnessController.brightnessPercent
            available: area.audioBrightnessController.brightnessAvailable
            onAdjusted: steps => area.audioBrightnessController.adjustBrightness(steps)
        }
    }
    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: 1; height: 14
        color: Theme.separator
    }
    Row {
        spacing: 5
        height: 26
        UpdatesIndicator { }
        RemovableMediaIndicator {
            id: removableMediaIndicator
            onToggleRequested: area.toggleRemovableMediaRequested()
        }
        ClipboardIndicator { open: area.clipboardOpen; onToggled: area.toggleClipboardRequested() }
        ControlCenterButton { open: area.controlCenterOpen; onToggled: area.toggleControlCenterRequested() }
    }
    Rectangle {
        visible: tray.implicitWidth > 0
        anchors.verticalCenter: parent.verticalCenter
        width: 1; height: 14
        color: Theme.separator
    }
    Tray { id: tray; barWindow: area.barWindow }
}
