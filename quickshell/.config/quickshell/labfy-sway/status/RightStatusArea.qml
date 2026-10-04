import QtQuick
import "../controlcenter"
import "../systemmonitor"

Row {
    id: area
    required property var barWindow
    required property var wifiDevice
    required property var adapter
    required property bool controlCenterOpen
    required property bool systemMonitorOpen
    signal openPageRequested(int page)
    signal toggleControlCenterRequested()
    signal toggleSystemMonitorRequested()
    function refreshBatteryThreshold() { batteryIndicator.refreshThreshold() }
    spacing: 5
    height: 26

    NetworkIndicator { wifiDevice: area.wifiDevice; onActivated: area.openPageRequested(1) }
    BluetoothIndicator { adapter: area.adapter; onActivated: area.openPageRequested(2) }
    BatteryIndicator { id: batteryIndicator; onActivated: area.openPageRequested(5) }
    UpdatesIndicator { }
    Tray { barWindow: area.barWindow }
    SystemMonitorButton {
        open: area.systemMonitorOpen
        onToggled: area.toggleSystemMonitorRequested()
    }
    ControlCenterButton { open: area.controlCenterOpen; onToggled: area.toggleControlCenterRequested() }
}
