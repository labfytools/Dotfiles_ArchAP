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
    function refreshBatteryThreshold() { batteryIndicator.refreshThreshold() }
    spacing: 5
    height: 26

    NetworkIndicator { wifiDevice: area.wifiDevice; onActivated: area.openPageRequested(1) }
    BluetoothIndicator { adapter: area.adapter; onActivated: area.openPageRequested(2) }
    BatteryIndicator { id: batteryIndicator; onActivated: area.openPageRequested(5) }
    UpdatesIndicator { }
    Tray { barWindow: area.barWindow }
    ControlCenterButton { open: area.controlCenterOpen; onToggled: area.toggleControlCenterRequested() }
}
