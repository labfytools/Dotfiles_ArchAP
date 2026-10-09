.pragma library

// CONTRACT: chaque identité de périphérique a une première valeur de référence,
// qui ne représente jamais une action. Les valeurs brutes détectent aussi les
// changements arrondis vers le même pourcentage affiché.
function observe(previous, identity, available, raw, muted) {
    if (!identity || !available || !Number.isFinite(raw))
        return { state: null, changed: false, volumeChanged: false, muteChanged: false };
    const state = { identity: identity, raw: raw, muted: !!muted };
    if (!previous || previous.identity !== identity)
        return { state: state, changed: false, volumeChanged: false, muteChanged: false };
    const volumeChanged = previous.raw !== raw;
    const muteChanged = previous.muted !== !!muted;
    return { state: state, changed: volumeChanged || muteChanged,
        volumeChanged: volumeChanged, muteChanged: muteChanged };
}

function nextCard(card, kind, value, muted, screen, now) {
    return { kind: kind, value: value, muted: muted, screen: screen, deadline: now + 1500,
        generation: card ? card.generation + 1 : 1 };
}

function expire(card, generation, now) {
    return !!card && card.generation === generation && now >= card.deadline;
}

function screenForEvent(screens, focusedName, origin, kind, now) {
    if (origin && origin.kind === kind && origin.until >= now
            && screens.indexOf(origin.screen) >= 0) return origin.screen;
    return screens.find(screen => screen.name === focusedName) || screens[0] || null;
}

function pageShows(kind, page) {
    return kind === "brightness" ? page === 0
        : kind === "microphone" ? page === 15 : page === 0 || page === 15;
}
