// CONTRACT: pixelDelta et angleDelta décrivent le même événement : choisir
// une seule source. 120 unités angulaires valent un cran de souris ; le seuil
// pixel est une valeur initiale à calibrer sur le touchpad réel.
function advance(state, pixel, angle, inverted, phase, touchpad) {
    if (phase === 3) return { remainder: 0, source: "", steps: 0 };
    const source = pixel !== 0 ? "pixel" : "angle";
    // WHY: sur le touchpad ASUS, le signe normalisé de V2 produisait
    // l'action opposée au mouvement physique observé. Une seule correction
    // s'applique ici, après la normalisation de QWheelEvent.inverted.
    const delta = (source === "pixel" ? pixel : angle)
        * (inverted ? -1 : 1) * (touchpad ? -1 : 1);
    if (!delta) return { remainder: state.remainder, source: state.source, steps: 0 };
    const threshold = source === "pixel" ? 32 : 120;
    let remainder = state.source === source ? state.remainder : 0;
    if (phase === 1 || (remainder !== 0 && Math.sign(remainder) !== Math.sign(delta)))
        remainder = 0;
    remainder += delta;
    const count = Math.trunc(remainder / threshold);
    const steps = count === 0 ? 0 : count;
    return { remainder: remainder - steps * threshold, source: source, steps: steps };
}
