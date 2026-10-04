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
            if (value.version === 1 && flavors.includes(value.effectiveFlavor)
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
            effectiveAccent: effectiveAccent, revision: revision });
    }
}
