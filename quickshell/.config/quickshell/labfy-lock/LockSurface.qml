import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Services.UPower
import Quickshell.Services.Mpris

WlSessionLockSurface {
    id: surface
    required property var controller
    required property bool secure
    property alias field: content.field
    color: "#1e1e2e"
    readonly property var battery: UPower.displayDevice
    readonly property string notificationPath: (Quickshell.env("XDG_RUNTIME_DIR") || "")
        + "/labfy-lock-notifications.json"
    FileView { id: notificationFile; path: surface.notificationPath; printErrors: false }
    readonly property var notificationData: {
        try {
            const raw = notificationFile.text();
            if (raw.length > 4096) return null;
            const data = JSON.parse(raw);
            if (data.version !== 1 || !Number.isSafeInteger(data.total) || data.total < 0
                    || data.total > 200 || !Array.isArray(data.apps)) return null;
            return { total: data.total, apps: data.apps.slice(0, 4).filter(item => item
                && typeof item.name === "string" && /^[^\r\n\t]{1,48}$/.test(item.name)
                && Number.isSafeInteger(item.count) && item.count >= 0 && item.count <= 200
                && typeof item.icon === "string" && /^[A-Za-z0-9_.-]{0,64}$/.test(item.icon)) };
        } catch (_) { return null; }
    }
    readonly property var player: {
        const items = Mpris.players.values.filter(item => item
            && item.dbusName !== "org.mpris.MediaPlayer2.playerctld"
            && item.trackTitle && item.trackTitle.trim().length);
        items.sort((a, b) => a.dbusName.localeCompare(b.dbusName));
        return items.find(item => item.playbackState === MprisPlaybackState.Playing)
            || items.find(item => item.playbackState === MprisPlaybackState.Paused) || null;
    }
    Component.onCompleted: controller.addSurface(surface)
    Component.onDestruction: controller.removeSurface(surface)

    // CONTRACT: the shared visual component owns presentation and input focus;
    // the lock, PAM conversation, and privacy-filtered data stay on this surface.
    LockContent {
        id: content
        anchors.fill: parent
        controller: surface.controller
        hostSurface: surface
        player: surface.player
        notificationData: surface.notificationData
        battery: surface.battery
    }
}
