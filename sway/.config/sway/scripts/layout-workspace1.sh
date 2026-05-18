#!/bin/bash
# ~/.config/sway/scripts/layout-workspace1.sh

# Attend que toutes les fenêtres soient créées
sleep 6

swaymsg 'workspace 1'
swaymsg '[app_id="kitty-1"] focus; move left'
swaymsg '[app_id="kitty-2"] focus; move down'
swaymsg '[title="Perplexity"] focus; move right'
