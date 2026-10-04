import QtQuick
import Quickshell.Bluetooth

QuickToggle {
    id: tile
    required property var adapter

    readonly property var connectedDevices: adapter && adapter.devices
        ? adapter.devices.values.filter(device => device.connected) : []

    title: "Bluetooth"
    icon: ""
    active: adapter !== null && adapter.enabled
    toggleEnabled: adapter !== null
    subtitle: !adapter ? "Indisponible" : !adapter.enabled ? "Désactivé"
        : connectedDevices.length === 1 ? connectedDevices[0].name
        : connectedDevices.length > 1 ? connectedDevices.length + " appareils" : "Activé"

    onToggleRequested: {
        if (adapter) adapter.enabled = !adapter.enabled;
    }
}
