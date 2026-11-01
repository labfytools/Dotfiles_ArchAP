# Moniteur matériel V1

`MonitorService.qml` est créé une seule fois par `ShellRoot`. Chaque barre ne
possède qu'un indicateur et charge `MonitorPanel.qml` pendant l'ouverture.
Le collecteur lance `backend.py` directement, sans shell ni démon. Le minuteur
est arrêté lorsque `activeOutput` est vide. Une nouvelle ouverture efface les
références différentielles CPU, réseau et processus. Les courbes restent en
mémoire, avec au plus 600 points par métrique ; aucune donnée n'est persistée.

Cadence : CPU, RAM, PSI et réseau chaque seconde ; GPU et températures toutes
les deux secondes ; stockage toutes les 30 secondes ; processus toutes les
quatre secondes uniquement dans la page Processus. Le stockage est obtenu par
`statvfs('/')` : `used` est l'occupation logique signalée par le système de
fichiers et `available` l'espace utilisable pour l'utilisateur. Ce n'est pas
une mesure de l'allocation interne des chunks Btrfs.

Le CPU des processus est exprimé en pourcentage d'un cœur logique. Les PID
sont associés à l'heure de démarrage du processus avant tout calcul de delta.
La mémoire « utilisée » est `MemTotal - MemAvailable`; le cache reste une
information distincte, non additive. VRAM et GTT sont affichées séparément.
PSI décrit le temps d'attente mémoire, sans rapport direct avec le taux de RAM
occupée. Les capteurs et compteurs absents restent indisponibles.

Validation physique restante : ouverture et fermeture au clic extérieur et
Échap ; coexistence Date Center, Control Center, Overview ; dimensions à
l'échelle fractionnaire ; charge et RSS du processus QuickShell sur dix minutes
et après plusieurs ouvertures ; comportement après veille. La session SwayFX
et le service QuickShell de production ne sont pas redémarrés pour cette étape.

## STEP15B2 — tableau de bord

L'interface utilise une grille CPU/GPU, mémoire/processus et stockage/réseau.
Sur écran large, le panneau vise 90 % de la largeur utilisable et 82 % de la
hauteur utilisable, avec des plafonds de 1500 × 920 unités logiques. Le contenu
secondaire défile dans un `Flickable` ; sous 850 unités logiques de largeur,
les blocs passent en une colonne. Les processus restent visibles dans le
contenu principal et leur lecture est liée à la visibilité du panneau. Leur
tri CPU/RAM est local à l'interface ; le collecteur et ses formules restent
inchangés. Les courbes sont dessinées par `Canvas` sans créer un item par point.

La fixture `tests/systemmonitor/visual.py` utilise un Sway headless isolé et
désactive seulement son grab de popup, car un xdg_popup avec grab exige une
entrée utilisateur réelle. La fermeture extérieure et Échap doivent donc
être contrôlés sur l'écran physique.
