#!/usr/bin/env bash
set -e

# Laisser le temps aux fenêtres de se lancer
sleep 5

# Aller sur le workspace 1
swaymsg "workspace 1"

# Regrouper les trois fenêtres sur le bon workspace (au cas où)
swaymsg '[app_id="kitty-1"] move to workspace 1'
swaymsg '[app_id="kitty-2"] move to workspace 1'
swaymsg '[title="Perplexity"] move to workspace 1'

# Layout horizontal global
swaymsg '[app_id="kitty-1"] focus'
swaymsg 'move left'

# Revenir sur la zone gauche (un des kitty)
swaymsg '[app_id="kitty-2"] focus'
swaymsg 'move down'

# Envoyer Perplexity à droite
swaymsg '[title="Perplexity"] focus'
swaymsg 'move right'

# Envoyer Perplexity à droite
swaymsg '[title="Perplexity"] focus'
swaymsg 'move right'
