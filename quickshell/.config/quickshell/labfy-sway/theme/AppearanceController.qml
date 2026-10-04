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
            if ((value.version === 1 || value.version === 2) && flavors.includes(value.effectiveFlavor)
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
    property bool wallpaperApplying: false
    property string wallpaperError: ""
    signal wallpaperApplied()

    Process {
        id: wallpaperWriter
        stdout: StdioCollector { id: wallpaperOutput; waitForEnd: true }
        stderr: StdioCollector { id: wallpaperErrors; waitForEnd: true }
        onExited: (code, status) => {
            appearance.wallpaperApplying = false;
            if (code !== 0 || status !== 0) {
                appearance.wallpaperError = wallpaperErrors.text.trim() || "Application impossible";
                return;
            }
            try {
                const state = JSON.parse(wallpaperOutput.text);
                if (!state.effectiveWallpaper || !Number.isSafeInteger(state.revision)) throw new Error("État invalide");
                appearance.effectiveWallpaper = state.effectiveWallpaper;
                appearance.wallpaperMode = state.wallpaperMode;
                appearance.revision = state.revision;
                appearance.wallpaperApplied();
            } catch (_) { appearance.wallpaperError = "Réponse wallpaper invalide"; }
        }
    }

    function applyWallpaper(path) {
        if (wallpaperApplying || !path || path === effectiveWallpaper) return false;
        wallpaperError = "";
        wallpaperApplying = true;
        wallpaperWriter.command = ["python", wallpaperBackend, "apply", path];
        wallpaperWriter.running = true;
        return true;
    }

    // INVARIANT: une paire refusée ne change aucun champ ni la révision.
    // La révision avance une seule fois après tout changement effectif.
    function applyTheme(flavor, accent) {
        if (!flavors.includes(flavor) || !accents.includes(accent)) return false;
        if (effectiveFlavor === flavor && effectiveAccent === accent
                && effectiveMode === "normal" && !effectiveHighContrast) return true;
        effectiveFlavor = flavor;
        effectiveAccent = accent;
        effectiveMode = "normal";
        effectiveHighContrast = false;
        revision++;
        return true;
    }

    function effectiveState() {
        return JSON.stringify({ effectiveFlavor: effectiveFlavor,
            effectiveMode: effectiveMode, effectiveDark: effectiveDark,
            effectiveHighContrast: effectiveHighContrast,
            effectiveAccent: effectiveAccent, effectiveWallpaper: effectiveWallpaper,
            wallpaperMode: wallpaperMode, wallpaperDirectory: wallpaperDirectory,
            revision: revision });
    }
}
