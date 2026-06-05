#!/bin/sh

BAT="BAT1"
THRESHOLD=20
STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/battery-low-notified"

capacity=$(cat /sys/class/power_supply/$BAT/capacity 2>/dev/null)
bat_status=$(cat /sys/class/power_supply/$BAT/status 2>/dev/null)

[ -z "$capacity" ] && exit 0
[ -z "$bat_status" ] && exit 0

if [ "$bat_status" = "Discharging" ] && [ "$capacity" -le "$THRESHOLD" ]; then
    if [ ! -f "$STATE_FILE" ]; then
        notify-send -u critical -t 10000 "Batterie faible" "Batterie à ${capacity}% — branche le chargeur."
        touch "$STATE_FILE"
    fi
else
    rm -f "$STATE_FILE"
fi
