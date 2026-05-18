# sway-config

![Screenshot](./assets/screen.jpg)

Personal SwayFX configuration, modular and lightweight, designed for everyday Wayland use.

## Layout

```bash
❯ tree .config/sway.config/sway
├── README.md
├── assets
│   └── screen.jpg
├── autostart.conf
├── bar.conf
├── bind.conf
├── catppuccin-mocha
├── config
├── i3status.toml
├── input.conf
├── layout.conf
├── rules.conf
├── scripts
│   └── inactive-windows-transparency.py
└── swayfx.confbash
```

## Dependencies

### Compositor and session
- swayfx
- swaylock
- swayidle

### Bar and status
- i3status-rs

### Base tools
- kitty
- firefox
- google-chrome-stable
- wl-clipboard
- grim
- slurp
- cliphist
- wlsunset
- brightnessctl
- powerprofilesctl
- swaync
- nm-connection-editor
- playerctl

### Audio / Bluetooth
- pipewire
- wireplumber
- blueman

### Launching / scripts
- bash

## Config structure

The configuration is split into several included files to keep it readable and easy to maintain.

- `input.conf`: keyboard, touchpad, French layout.
- `layout.conf`: wallpaper, theme, borders, gaps.
- `bind.conf`: keyboard shortcuts.
- `bar.conf`: Sway bar and i3status-rs.
- `autostart.conf`: services started on session launch.
- `rules.conf`: window placement and floating rules.
- `i3status.toml`: i3status-rs configuration.

## Appearance

The theme is based on Catppuccin Macchiato, with dark colors, a top bar, and thin borders.  
The wallpaper is loaded with `output * bg ... fill`, and the main output is positioned with `position 1920,0` in the current config.

## Keyboard

The keyboard is configured for French with the `oss` variant.

Example:
- layout: `fr`
- variant: `oss`

## Status bar

The Sway bar is placed at the top and uses `i3status-rs` as its backend.

The `i3status.toml` file includes:
- workspaces,
- focused window,
- music,
- Bluetooth,
- network,
- sound,
- brightness,
- battery,
- power profile,
- notification,
- power menu,
- tray.

## Autostart

On startup, the config launches:
- `wlsunset` for blue light reduction,
- `wl-paste --watch cliphist store` for clipboard history,
- `swayidle` for automatic locking and screen power management.
- `swaync`

## Keybinds

Some important shortcuts:
- `Mod + Return`: open the terminal.
- `Mod + q`: close the focused window.
- `Mod + Shift + e`: exit Sway via `swaynag`.
- `Mod + r`: resize mode.
- `Mod + Shift + c`: reload the config.
- `Mod + Ctrl + l`: lock the screen.
- `Print`: capture a selected area to the clipboard.
- `Shift + Print`: capture the full screen to the clipboard.
- `Mod + Ctrl + e`: launcher wofi
- `Mod + v`: wofi cliphist
- `Mod + F9``Mod + F10``Mod + F11`: power profiles

## Power profiles

The bar includes a `powerprofilesctl` block with:
- `performance`,
- `balanced`,
- `power-saver`.

The related keybinds are:
- `Mod + F9`: power-saver.
- `Mod + F10`: balanced.
- `Mod + F11`: performance.

## Floating windows

Some windows are forced into floating mode and centered:
- `blueman-manager`
- `pavucontrol`
- `nm-connection-editor`

## Audio

Audio shortcuts use `pactl` on the default sink.  
Volume is also handled in i3status-rs with a `sound` block.

## Useful commands

Reload Sway:
```bash
swaymsg reload
```

Exit Sway:
```bash
swaymsg exit
```

Restart the bar:
```bash
pkill swaybar
swaymsg reload
```

## Notes

This config is meant to stay simple, stable, and easy to modify.  
The setup is clearly Wayland-native, with minimal unnecessary layers and a modular structure.
