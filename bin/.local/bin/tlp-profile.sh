#!/bin/sh

# Récupère la ligne "TLP profile    = balanced/BAT" et isole "balanced/BAT"
profile=$(tlp-stat -s 2>/dev/null | awk -F'= ' '/TLP profile/ {print $2}')

# Optionnel : ne garder que le profil logique (performance/balanced/power-saver)
# profile=$(printf "%s" "$profile" | cut -d'/' -f1)

[ -z "$profile" ] && profile="unknown"
printf " %s\n" "$profile"
