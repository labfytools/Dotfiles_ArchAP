#!/usr/bin/env bash

# Récupère le profil TLP courant (AC ou BAT)
profile=$(tlp-stat -s 2>/dev/null | awk '/Power source/ {print $4}')

# Si TLP n'est pas dispo
if [ -z "$profile" ]; then
  echo '{"text": "TLP?", "tooltip": "TLP not available", "class": "tlp-unknown"}'
  exit 0
fi

case "$profile" in
  AC)
    text="AC"
    icon="󱐋"        # icône optionnelle, change selon ta police
    class="tlp-ac"
    tooltip="TLP profile: AC (performance)"
    ;;
  battery|BAT)
    text="BAT"
    icon="󰁹"
    class="tlp-bat"
    tooltip="TLP profile: Battery (powersave)"
    ;;
  *)
    text="$profile"
    icon="󰂄"
    class="tlp-unknown"
    tooltip="TLP profile: $profile"
    ;;
esac

printf '{"text": "%s %s", "tooltip": "%s", "class": "%s"}\n' "$icon" "$text" "$tooltip" "$class"
