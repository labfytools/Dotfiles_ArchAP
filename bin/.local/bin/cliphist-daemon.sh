#!/bin/sh
wl-paste --type text --watch cliphist store &
wl-paste --type image --watch cliphist store &
wait
