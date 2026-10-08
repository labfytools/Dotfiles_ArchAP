// CONTRACT: les deux contrôles appliquent des points de pourcentage absolus ;
// leur plancher diffère, mais aucun ne peut dépasser 100 %.
function bounded(value, minimum) {
    return Math.max(minimum, Math.min(100, Math.round(value)));
}
