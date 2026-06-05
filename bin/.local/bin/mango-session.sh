#!/bin/sh
systemctl --user start graphical-session.target || true
exec mango
