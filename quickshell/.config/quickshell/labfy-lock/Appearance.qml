import QtQuick
import Quickshell
import Quickshell.Io

QtObject {
    id: appearance
    // CONTRACT: this reads only the effective state written by the existing
    // appearance controller. It never runs a second controller or writes it.
    readonly property string path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state")
        + "/labfy-appearance/effective.json"
    property FileView stateFile: FileView { path: appearance.path; blockLoading: false; printErrors: false }
    property FileView preferenceFile: FileView {
        path: (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config")
            + "/quickshell/labfy-lock/preferences.json"
        printErrors: false
    }
    property FileView paletteFile: FileView {
        path: (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config")
            + "/quickshell/labfy-sway/theme/catppuccin.json"
        blockLoading: false
        printErrors: false
    }
    readonly property var state: {
        try {
            const value = JSON.parse(stateFile.text());
            return value && typeof value === "object" ? value : {};
        } catch (_) { return {}; }
    }
    readonly property string wallpaper: typeof state.effectiveWallpaper === "string"
        && state.effectiveWallpaper.startsWith("/") ? "file://" + state.effectiveWallpaper : ""
    readonly property string mediaVisibility: {
        // CONTRACT: an explicit privacy preference wins; without one, show
        // available local artwork and metadata as requested by the V3 layout.
        try {
            const value = JSON.parse(preferenceFile.text());
            return value.version === 1 && ["hidden", "generic", "metadata"].includes(value.media)
                ? value.media : "metadata";
        } catch (_) { return "metadata"; }
    }
    readonly property var palette: {
        try {
            const palettes = JSON.parse(paletteFile.text());
            return palettes[state.effectiveFlavor] || palettes.mocha || {};
        } catch (_) { return {}; }
    }
    readonly property color base: palette.base || "#1e1e2e"
    readonly property color surface: palette.surface0 || "#313244"
    readonly property color foreground: palette.text || "#ffffff"
    readonly property color accent: palette[state.effectiveAccent] || "#b4befe"
}
