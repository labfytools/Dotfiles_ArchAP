pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: theme

    // CONTRACT: la palette officielle versionnée est l'unique source des quatre flavors.
    // Le chargement bloquant unique précède l'évaluation des couleurs des fenêtres.
    FileView {
        id: paletteFile
        path: Qt.resolvedUrl("catppuccin.json")
        blockLoading: true
    }
    readonly property var palettes: JSON.parse(paletteFile.text())
    readonly property string flavor: AppearanceController.effectiveFlavor
    readonly property string accentName: AppearanceController.effectiveAccent
    readonly property var palette: palettes[flavor]

    function setFlavor(value) {
        return AppearanceController.applyTheme(value, accentName);
    }
    function setAccent(value) {
        return AppearanceController.applyTheme(flavor, value);
    }
    readonly property var accentNames: AppearanceController.accents

    readonly property color rosewater: palette.rosewater
    readonly property color flamingo: palette.flamingo
    readonly property color pink: palette.pink
    readonly property color mauve: palette.mauve
    readonly property color red: palette.red
    readonly property color maroon: palette.maroon
    readonly property color peach: palette.peach
    readonly property color yellow: palette.yellow
    readonly property color green: palette.green
    readonly property color teal: palette.teal
    readonly property color sky: palette.sky
    readonly property color sapphire: palette.sapphire
    readonly property color blue: palette.blue
    readonly property color lavender: palette.lavender
    readonly property color text: palette.text
    readonly property color subtext1: palette.subtext1
    readonly property color subtext0: palette.subtext0
    readonly property color overlay2: palette.overlay2
    readonly property color overlay1: palette.overlay1
    readonly property color overlay0: palette.overlay0
    readonly property color surface2: palette.surface2
    readonly property color surface1: palette.surface1
    readonly property color surface0: palette.surface0
    readonly property color base: palette.base
    readonly property color mantle: palette.mantle
    readonly property color crust: palette.crust

    // CONTRACT: l'alpha de la barre est un profil UI, jamais une entrée Catppuccin.
    // CONTRACT: les composants lisent des rôles ; seul l'état effectif choisit
    // les surfaces et limites du profil haute visibilité.
    readonly property bool highContrast: AppearanceController.effectiveHighContrast
    readonly property real panelOpacity: highContrast ? 1.0 : 235 / 255
    readonly property real popupOpacity: 1.0
    readonly property color panelBackground: Qt.rgba(base.r, base.g, base.b, panelOpacity)
    readonly property color popupBackground: base
    // INVARIANT: même sur hover/pressed, le texte garde au moins 4,5:1 ;
    // surface1/surface2 Latte et surface2 Frappé sont trop proches du texte.
    readonly property color buttonBackground: highContrast && flavor === "latte" ? mantle : surface0
    readonly property color buttonHover: highContrast && flavor === "latte" ? surface0 : surface1
    readonly property color buttonPressed: highContrast ? (flavor === "latte" ? surface0 : surface1) : surface2
    readonly property color foreground: text
    // Latte sur surface0 a besoin d'un texte plus sombre que subtext0.
    readonly property color secondaryForeground: highContrast ? text : flavor === "latte" ? text : subtext0
    readonly property color disabledForeground: flavor === "latte" ? subtext1 : overlay0
    // Plusieurs contrôles historiques utilisent border comme fond de hover :
    // ce rôle doit donc rester compatible avec le contraste du texte.
    readonly property color border: highContrast && flavor === "latte" ? surface0 : surface1
    readonly property color strongBorder: highContrast ? overlay2 : surface2
    readonly property color outline: highContrast ? overlay2 : border
    readonly property color emphasisBackground: highContrast ? buttonHover : strongBorder
    readonly property color accent: palette[accentName]
    // WHY: Lavender Latte n'offre aucun texte Catppuccin à contraste 4.5:1.
    // Choisir le noir ou le blanc technique par contraste WCAG pour chaque accent.
    function luminance(c) {
        const channel = x => x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
        return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
    }
    function contrastingText(background) {
        return luminance(background) > 0.179 ? "#000000" : "#ffffff";
    }
    readonly property color onAccent: contrastingText(accent)
    // Latte Lavender ne contraste pas assez avec base pour du texte nu.
    readonly property color accentForeground: flavor === "latte" ? text : accent
    readonly property color focus: accent
    readonly property color urgent: peach
    readonly property color warning: yellow
    readonly property color warningForeground: flavor === "latte" ? text : yellow
    readonly property color success: green
    readonly property color danger: red
    readonly property color urgentForeground: flavor === "latte" ? text : peach
    readonly property color successForeground: flavor === "latte" ? text : green
    readonly property color shadow: highContrast ? "#00000077" : "#00000055"
    readonly property color separator: highContrast ? overlay1 : surface1
    readonly property color inputBackground: highContrast ? surface0 : surface0
    readonly property color inputBorder: highContrast ? overlay2 : surface2
    readonly property color selectedBackground: accent
    readonly property color selectedForeground: onAccent
}
