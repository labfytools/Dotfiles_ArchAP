import QtQuick
import "../controlcenter"

Row {
    id: area
    required property var barWindow
    required property var wifiDevice
    required property var adapter
    required property bool controlCenterOpen
    signal openPageRequested(int page)
    signal toggleControlCenterRequested()
    signal toggleRemovableMediaRequested()
    function refreshBatteryThreshold() { batteryIndicator.refreshThreshold() }
    function closeRemovableMedia() { removableMediaIndicator.popupOpen = false }
    function setRemovableMediaOpen(open) { removableMediaIndicator.popupOpen = open }
    readonly property bool removableMediaOpen: removableMediaIndicator.popupOpen
    spacing: 5
    height: 26

    NetworkIndicator { wifiDevice: area.wifiDevice; onActivated: area.openPageRequested(1) }
    BluetoothIndicator { adapter: area.adapter; onActivated: area.openPageRequested(2) }
    BatteryIndicator { id: batteryIndicator; onActivated: area.openPageRequested(5) }
    UpdatesIndicator { }
    RemovableMediaIndicator {
        id: removableMediaIndicator
        onToggleRequested: area.toggleRemovableMediaRequested()
    }
    Tray { barWindow: area.barWindow }
    ControlCenterButton { open: area.controlCenterOpen; onToggled: area.toggleControlCenterRequested() }
}
