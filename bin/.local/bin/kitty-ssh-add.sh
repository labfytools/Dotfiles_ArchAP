#!/usr/bin/env bash
set -e

cd "$HOME"

# lance ssh-add dans ce kitty
ssh-add "$HOME/.ssh/id_ed25519-admin"

# quand c'est fini, on lance un shell interactif normal
exec zsh
