// CONTRACT: les indicateurs système utilisent le même espace avant « % » et
// signalent explicitement l'absence de valeur sans afficher un faux zéro.
function label(available, percent) {
    return available ? percent + " %" : "—";
}
