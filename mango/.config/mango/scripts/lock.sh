#!/usr/bin/env bash

img="/tmp/gtklock-shot.png"
blur="/tmp/gtklock-blur.png"

grim "$img"
magick "$img" -blur 0x14 -brightness-contrast -8x-5 "$blur"

pidof gtklock || gtklock -d
