#!/bin/sh
# Adaptation du wrapper Yazi de hunkyburrito/xdg-desktop-portal-termfilechooser 1.4.3.
# CONTRACT: arguments multiple, directory, save, path, out, debug dans cet ordre.
set -eu

if [ "${1:-}" != '--session' ]; then
    # WHY: kitty reçoit des arguments distincts ; aucun chemin n'est réinterprété par un shell.
    # INVARIANT: l'app_id est réservé à ce sélecteur, jamais aux terminaux ordinaires.
    # CONTRACT: dimension initiale 1000x650, bornée à la sortie SwayFX active.
    width=1000
    height=650
    if command -v swaymsg >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
        geometry=$(swaymsg -t get_outputs -r 2>/dev/null | jq -r '[.[] | select(.focused == true and .active == true)] | first | if . then "\(.rect.width) \(.rect.height)" else empty end' 2>/dev/null) || geometry=''
        if [ -n "$geometry" ]; then
            output_width=${geometry%% *}
            output_height=${geometry#* }
            case "$output_width:$output_height" in
                *[!0-9:]* ) ;;
                * )
                    [ "$output_width" -le 1040 ] && width=$(( output_width > 80 ? output_width - 40 : 40 ))
                    [ "$output_height" -le 690 ] && height=$(( output_height > 80 ? output_height - 40 : 40 ))
                    ;;
            esac
        fi
    fi
    exec kitty --class labfy-yazi-filechooser --title 'Yazi · Sélecteur de fichiers' \
        --override remember_window_size=no \
        --override "initial_window_width=${width}" \
        --override "initial_window_height=${height}" \
        -- "$0" --session "$@"
fi
shift

multiple=${1:?}
directory=${2:?}
save=${3:?}
path=${4:?}
out=${5:?}
debug=${6:-0}

case "$multiple:$directory:$save:$debug" in
    *[!01:]* ) exit 2 ;;
esac

# CONTRACT: Yazi utilise sa configuration XDG normale ; chooser-file contient
# les chemins sélectionnés, tandis que cwd-file sert au choix du dossier courant.
if [ "$directory" = 1 ]; then
    yazi --chooser-file="$out" --cwd-file="$out.1" "$path" || :
    if [ ! -s "$out" ] && [ -s "$out.1" ]; then
        cat "$out.1" > "$out"
    fi
    rm -f -- "$out.1"
else
    yazi --chooser-file="$out" "$path" || :
fi

if [ "$save" = 1 ] && [ -s "$out" ]; then
    # WHY: le backend peut proposer un fichier existant. La confirmation garde
    # l'écrasement potentiel explicite avant de publier le chemin à l'appelant.
    printf '\nDestination sélectionnée : %s\nConfirmer ? L’application peut écraser son contenu. [o/N] ' "$(head -n 1 -- "$out")"
    IFS= read -r reply </dev/tty || reply=''
    case "$reply" in
        o|O|oui|Oui|OUI) ;;
        *) : > "$out" ;;
    esac
fi
