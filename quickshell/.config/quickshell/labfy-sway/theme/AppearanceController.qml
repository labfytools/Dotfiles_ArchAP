pragma Singleton
import Quickshell
import Quickshell.Io

Singleton {
    id: appearance
    // CONTRACT: état effectif unique du bureau. Les futurs adaptateurs ne
    // déduisent jamais Light/Dark du nom de flavor ; ils lisent effectiveDark.
    // 17B ne définit que le mode normal ; les décisions Sun arrivent après.
    readonly property var flavors: ["latte", "frappe", "macchiato", "mocha"]
    readonly property var accents: ["rosewater", "flamingo", "pink", "mauve", "red", "maroon", "peach", "yellow", "green", "teal", "sky", "sapphire", "blue", "lavender"]
    readonly property string defaultWallpaper: "/usr/share/backgrounds/sway/Sway_Wallpaper_Blue_1920x1080.png"
    readonly property string wallpaperBackend: (Quickshell.env("HOME") || "/home/fy59") + "/.local/bin/wallpaper-manager.py"
    readonly property string nightLightBackend: (Quickshell.env("HOME") || "/home/fy59") + "/.local/bin/night-light-manager.py"
    // CONTRACT: le backend écrit cet état atomiquement après validation Sway.
    // Le repli Mocha fonctionne avant la première génération ; aucune lecture
    // par frame ni polling. Les futurs adaptateurs lisent cet état via l'IPC.
    FileView {
        id: stateFile
        path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state")
              + "/labfy-appearance/effective.json"
        blockLoading: true
        printErrors: false
    }
    function initialState() {
        try {
            const value = JSON.parse(stateFile.text());
            if ((value.version === 1 || value.version === 2 || value.version === 3)
                    && flavors.includes(value.effectiveFlavor)
                    && accents.includes(value.effectiveAccent)
                    && value.effectiveMode === "normal") return value;
        } catch (_) {}
        return { effectiveFlavor: "mocha", effectiveAccent: "lavender", revision: 0 };
    }
    readonly property var initial: initialState()
    property string effectiveFlavor: initial.effectiveFlavor
    property string effectiveMode: "normal"
    readonly property bool effectiveDark: effectiveFlavor !== "latte"
    property bool effectiveHighContrast: false
    property string effectiveAccent: initial.effectiveAccent
    property int revision: Number.isSafeInteger(initial.revision) && initial.revision >= 0
        ? initial.revision : 0
    // CONTRACT: la sélection QML ne touche pas à ces propriétés ; le backend
    // ne publie le chemin et la révision qu'après reload et vérification swaybg.
    property string effectiveWallpaper: initial.effectiveWallpaper || defaultWallpaper
    property string wallpaperMode: "fill"
    property string wallpaperDirectory: ""
    property string themeMode: initial.themeMode === "wallpaper" ? "wallpaper" : "manual"
    property string manualFlavor: flavors.includes(initial.manualFlavor) ? initial.manualFlavor : effectiveFlavor
    property var wallpaperAnalysis: initial.wallpaperAnalysis || null
    // CONTRACT: le choix persistant reste distinct du mode effectif ; 17F
    // pourra suspendre la correction sans écraser la préférence utilisateur.
    property string nightLightMode: "auto"
    property string effectiveNightLightMode: "auto"
    property bool nightLightSuspended: false
    property int nightTemperature: 3000
    property int dayTemperature: 6500
    property bool nightScheduleConfigured: false
    property bool nightLightBusy: false
    property string nightLightError: ""
    property bool appearanceBusy: false
    property string appearanceError: ""
    property bool wallpaperApplying: false
    property string wallpaperError: ""
    property string operationKind: ""
    signal wallpaperApplied()
    signal appearanceApplied()

    // CONTRACT: effective.json est le dernier état appliqué valide. Le
    // backend réconcilie ses deux fichiers générés au démarrage, puis le QML
    // adopte exactement la révision persistée sans décision locale de thème.
    Process {
        id: startupReader
        command: ["python", appearance.wallpaperBackend, "status"]
        running: true
        stdout: StdioCollector { id: startupOutput; waitForEnd: true }
        stderr: StdioCollector { id: startupError; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0 || status !== 0) {
                appearance.appearanceError = startupError.text.trim() || "Réconciliation Appearance impossible";
                return;
            }
            try { appearance.acceptSnapshot(JSON.parse(startupOutput.text)); }
            catch (_) { appearance.appearanceError = "État Appearance invalide"; }
        }
    }
    function acceptSnapshot(value) {
        if (!value || !flavors.includes(value.effectiveFlavor)
                || value.effectiveAccent !== "lavender"
                || !Number.isSafeInteger(value.revision) || value.revision < 0
                || (value.themeMode !== "manual" && value.themeMode !== "wallpaper")
                || !flavors.includes(value.manualFlavor)
                || !value.effectiveWallpaper) return false;
        // Un status démarré avant une application ne peut pas revenir en
        // arrière après la publication IPC de la révision plus récente.
        if (value.revision < revision) return false;
        effectiveFlavor = value.effectiveFlavor;
        effectiveAccent = value.effectiveAccent;
        effectiveMode = "normal";
        effectiveHighContrast = false;
        effectiveWallpaper = value.effectiveWallpaper;
        wallpaperMode = "fill";
        themeMode = value.themeMode;
        manualFlavor = value.manualFlavor;
        wallpaperDirectory = value.wallpaperDirectory || wallpaperDirectory;
        wallpaperAnalysis = value.wallpaperAnalysis || value.analysis || null;
        if (value.nightLightMode === "off" || value.nightLightMode === "auto" || value.nightLightMode === "on")
            nightLightMode = value.nightLightMode;
        if (value.effectiveNightLightMode === "off" || value.effectiveNightLightMode === "auto" || value.effectiveNightLightMode === "on")
            effectiveNightLightMode = value.effectiveNightLightMode;
        if (typeof value.nightLightSuspended === "boolean") nightLightSuspended = value.nightLightSuspended;
        if (Number.isInteger(value.nightTemperature)) nightTemperature = value.nightTemperature;
        if (Number.isInteger(value.dayTemperature)) dayTemperature = value.dayTemperature;
        revision = value.revision;
        appearanceError = "";
        wallpaperError = "";
        return true;
    }

    function acceptPublished(payload) {
        try {
            const value = JSON.parse(payload);
            return acceptSnapshot(Object.assign({}, value.state, value.preferences));
        } catch (_) { return false; }
    }

    function acceptNightLight(value) {
        if (!value || !["off", "auto", "on"].includes(value.nightLightMode)
                || !["off", "auto", "on"].includes(value.effectiveNightLightMode)
                || !Number.isInteger(value.nightTemperature)
                || value.dayTemperature !== 6500) return false;
        nightLightMode = value.nightLightMode;
        effectiveNightLightMode = value.effectiveNightLightMode;
        nightLightSuspended = value.nightLightSuspended === true;
        nightTemperature = value.nightTemperature;
        dayTemperature = value.dayTemperature;
        nightScheduleConfigured = value.scheduleConfigured === true;
        nightLightError = "";
        return true;
    }
    function acceptPublishedNightLight(payload) {
        try { return acceptNightLight(JSON.parse(payload)); }
        catch (_) { return false; }
    }
    Process {
        id: nightStartup
        command: ["python", appearance.nightLightBackend, "reconcile"]
        running: true
        stdout: StdioCollector { id: nightStartupOutput; waitForEnd: true }
        stderr: StdioCollector { id: nightStartupError; waitForEnd: true }
        onExited: (code, status) => {
            if (code !== 0 || status !== 0) {
                appearance.nightLightError = nightStartupError.text.trim() || "Réconciliation Lumière nocturne impossible";
                return;
            }
            try { appearance.acceptNightLight(JSON.parse(nightStartupOutput.text)); }
            catch (_) { appearance.nightLightError = "État Lumière nocturne invalide"; }
        }
    }
    Process {
        id: nightWriter
        stdout: StdioCollector { id: nightOutput; waitForEnd: true }
        stderr: StdioCollector { id: nightErrors; waitForEnd: true }
        onExited: (code, status) => {
            appearance.nightLightBusy = false;
            if (code !== 0 || status !== 0) {
                appearance.nightLightError = nightErrors.text.trim() || "Application Lumière nocturne impossible";
                return;
            }
            try {
                if (!appearance.acceptNightLight(JSON.parse(nightOutput.text)))
                    appearance.nightLightError = "Réponse Lumière nocturne invalide";
            } catch (_) { appearance.nightLightError = "Réponse Lumière nocturne invalide"; }
        }
    }
    function runNightLight(args) {
        if (nightLightBusy) return false;
        nightLightBusy = true;
        nightLightError = "";
        nightWriter.command = ["python", nightLightBackend].concat(args);
        nightWriter.running = true;
        return true;
    }
    function setNightLightMode(mode) {
        if (!["off", "auto", "on"].includes(mode) || mode === nightLightMode) return false;
        return runNightLight(["set-mode", mode]);
    }
    function setNightTemperature(value) {
        if (!Number.isInteger(value) || value < 2500 || value > 5000 || value % 100 !== 0) return false;
        return runNightLight(["set-night-temperature", String(value)]);
    }

    Process {
        id: wallpaperWriter
        stdout: StdioCollector { id: wallpaperOutput; waitForEnd: true }
        stderr: StdioCollector { id: wallpaperErrors; waitForEnd: true }
        onExited: (code, status) => {
            appearance.appearanceBusy = false;
            appearance.wallpaperApplying = false;
            if (code !== 0 || status !== 0) {
                const message = wallpaperErrors.text.trim() || "Application impossible";
                if (message.includes("Analyse Auto Theme")) appearance.appearanceError = message;
                else appearance.wallpaperError = message;
                return;
            }
            try {
                const state = JSON.parse(wallpaperOutput.text);
                if (!appearance.acceptSnapshot(state)) throw new Error("État invalide");
                if (appearance.operationKind === "wallpaper") appearance.wallpaperApplied();
                appearance.appearanceApplied();
            } catch (_) { appearance.appearanceError = "Réponse Appearance invalide"; }
        }
    }

    function runOperation(args, applyingWallpaper) {
        if (appearanceBusy) return false;
        wallpaperError = "";
        appearanceError = "";
        appearanceBusy = true;
        wallpaperApplying = applyingWallpaper;
        operationKind = applyingWallpaper ? "wallpaper" : "theme";
        wallpaperWriter.command = ["python", wallpaperBackend].concat(args);
        wallpaperWriter.running = true;
        return true;
    }

    function applyWallpaper(path) {
        if (!path || path === effectiveWallpaper) return false;
        return runOperation(["apply", path], true);
    }
    function setThemeMode(mode) {
        if ((mode !== "manual" && mode !== "wallpaper") || mode === themeMode) return false;
        return runOperation(["set-theme-mode", mode], false);
    }
    function setManualFlavor(flavor) {
        if (!flavors.includes(flavor) || themeMode !== "manual"
                || flavor === manualFlavor && flavor === effectiveFlavor) return false;
        return runOperation(["set-manual-flavor", flavor], false);
    }

    // CONTRACT: l'ancien point d'entrée IPC délègue au backend persistant ;
    // il ne doit jamais créer un état QuickShell isolé de Sway/effective.json.
    function applyTheme(flavor, accent) {
        if (!flavors.includes(flavor) || accent !== "lavender"
                || themeMode !== "manual") return false;
        if (effectiveFlavor === flavor && manualFlavor === flavor) return true;
        return setManualFlavor(flavor);
    }

    function effectiveState() {
        return JSON.stringify({ effectiveFlavor: effectiveFlavor,
            effectiveMode: effectiveMode, effectiveDark: effectiveDark,
            effectiveHighContrast: effectiveHighContrast,
            effectiveAccent: effectiveAccent, effectiveWallpaper: effectiveWallpaper,
            wallpaperMode: wallpaperMode, wallpaperDirectory: wallpaperDirectory,
            themeMode: themeMode, manualFlavor: manualFlavor,
            nightLightMode: nightLightMode, effectiveNightLightMode: effectiveNightLightMode,
            nightLightSuspended: nightLightSuspended, nightTemperature: nightTemperature,
            dayTemperature: dayTemperature,
            revision: revision });
    }
}
