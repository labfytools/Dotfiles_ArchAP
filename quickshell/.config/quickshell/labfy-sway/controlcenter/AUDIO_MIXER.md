# Mixeur audio du Control Center

Le clic sur l'indicateur de volume de la barre ouvre la page **Audio** du
Control Center. Le défilement de la barre conserve ses pas de 1 point et son
contrôleur `VolumeSlider`. La page est intégrée au `StackLayout` existant et
possède un bouton Retour vers Réglages rapides ; elle ne crée ni fenêtre ni
service supplémentaire.

La page utilise `Quickshell.Services.Pipewire`. `Pipewire.nodes` fournit les
objets vivants et `PwObjectTracker` lie les nœuds audio uniquement tant que la
page est active. Le volume général lit exactement le `sinkAudio` du
`VolumeSlider` déjà partagé avec la barre. Les trois listes se fondent sur
`media.class` et les propriétés de direction : `Audio/Sink` pour les sorties,
`Audio/Source` pour les microphones et `Stream/Output/Audio` pour les flux de
lecture. Les flux de capture, de vidéo et les nœuds techniques de monitoring
ou de groupe loopback sont exclus. Chaque objet de flux garde sa propre ligne ;
aucune identité temporaire n'est persistée et l'ordre des survivants suit le
catalogue PipeWire pendant les interactions.

Choisir une sortie ou une entrée écrit `preferredDefaultAudioSink` ou
`preferredDefaultAudioSource`. La coche et le libellé « utilisée » suivent
uniquement `defaultAudioSink` et `defaultAudioSource` effectivement observés.
La préférence peut être différente de la valeur effective ou prendre du temps
à s'appliquer. Un changement de sortie par défaut ne garantit pas le transfert
des flux déjà ouverts. Le routage par application et les profils Bluetooth ne
font pas partie de cette V1.

Chaque curseur affiche le volume réel, borné à 0–100 % seulement pour une
nouvelle demande utilisateur. Une valeur externe supérieure à 100 % demeure
affichée sans écriture automatique. Le bouton muet est indépendant du curseur :
modifier le volume n'active jamais un flux ou un microphone muet. La page ne
lance aucune capture de microphone et n'écrit aucun paramètre à l'ouverture ou
à la fermeture. Les commandes restent des propriétés natives QuickShell ;
`wpctl` n'est utilisé que pour la confirmation des tests.

`AudioMixerModel.js` contient le filtrage et les conversions vérifiées par
`node tests/audio_mixer/test_model.js`. Les essais réels de V1 ont utilisé deux
flux `pw-play` silencieux et non reliés (`--target 0`) : leurs volumes ont été
réglés indépendamment depuis l'interface et confirmés par PipeWire. La
sourdine d'un flux est restée active après un déplacement de son curseur ; une
modification externe et une disparition pendant le réglage ont aussi été
reflétées dans la page. Aucun flux utilisateur n'a été modifié. Le choix réel
d'une autre sortie ou entrée et la sourdine matérielle du microphone restent à
contrôler manuellement, sans déconnecter la sortie courante ni activer le micro.
