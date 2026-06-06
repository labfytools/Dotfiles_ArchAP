# ArchAP – Arch Professor 

<p align="center">
  <img src="https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/screen.jpg" width="900" alt="Screenshot">
</p>

Personal Arch Linux configuration focused on: 

- Keyboard-driventerminal-first
- Terminal-first workflow with Sway and MangoWM, Neovim, Kitty
- Catppuccin Mocha themed UI.  
- Cyber Learning

**Goal** : 
all reproducible from a single install script and a GNU Stow‑managed dotfiles repo.
<p>

[Installation Guide](#installation-on-existing-system)
[Greetd/Regreet config](#regreet-config)
[Snapper install & config](#snapper-config)

## Status

ArchASP is currently in active development.


If you want to contribute, improve the codebase, suggest ideas, or help
shape the installer workflow, feel free to contribute to that repository
too.

---

## Overview

This repo contains my entire user configuration, including:

- Zsh shell configuration with plugins, history tuning, fuzzy-finding and Python helpers
- A Catppuccin Mocha desktop theme applied consistently across GTK 3/4, Qt
- Sway configuration split into modular files with custom keybinds, bar, rules and styling
- Neovim configuration using Lua, Lazy, Treesitter, LSP and a full plugin setup
- Kitty terminal configuration with a large theme collection and a current theme
- Extra configs for GTK, Qt, TUI tools (yazi, fastfetch, calcure, bat, eza, cliphist, i3status-rust)
- Systemd user services for background daemons (idle/lock, clipboard, theming, sync, etc.)

The goal is to provide an opinionated but reusable starting point for an Arch/Linux tiling window manager environment.

---

## Required packages

This setup assumes the following tools are installed (Arch package names):

- [swayfx](https://github.com/WillPower3309/swayfx) (Wayland tiling window manager)
- [swaylock-effects](https://github.com/mortie/swaylock-effects)
- [swayidle](https://github.com/swaywm/swayidle)
- [wofi](https://github.com/SimplyCEO/wofi) (Wayland application launcher)
- [i3status-rust](https://github.com/greshake/i3status-rust?tab=readme-ov-file) (status bar blocks)
- [kitty](https://github.com/kovidgoyal/kitty) (terminal emulator)
- [neovim](https://github.com/neovim/neovim) (text editor)
- [zsh](https://github.com/ohmyzsh/ohmyzsh/wiki/Installing-ZSH) (shell)
- [starship](https://github.com/starship/starship) (prompt)
- [fzf](https://github.com/junegunn/fzf) (fuzzy finder)
- [fd](https://github.com/sharkdp/fd) (fast file search, used by fzf)
- [ripgrep](https://github.com/burntsushi/ripgrep) (rg, fast grep)
- [eza](https://github.com/eza-community/eza) (ls replacement)
- [fastfetch](https://github.com/fastfetch-cli/fastfetch) (system info on shell startup)
- [yazi](https://github.com/sxyazi/yazi) (terminal file manager)
- [bat](https://github.com/sharkdp/bat) (cat replacement with syntax highlighting)
- [cliphist](https://github.com/sentriz/cliphist) (Wayland clipboard manager)
- [calcure](https://github.com/anufrievroman/calcure) (terminal calendar and tasks)
- [zoxide](https://github.com/ajeetdsouza/zoxide) (smart cd)
- [pyenv](https://github.com/jorgenschaefer/pyvenv) (Python version manager)
- [git](https://github.com/git/git) (version control)
- [yay](https://github.com/jguer/yay) (AUR helper)
- [gtk3](https://github.com/gooroom/gtk3)
- [gtk4](https://gitlab.gnome.org/GNOME/gtk/)
- [catppuccin-gtk-theme-mocha](https://github.com/catppuccin/gtk)
- [catppuccin-cursors-mocha](https://github.com/catppuccin/cursors)
- [greetd](https://github.com/kennylevinsen/greetd)
- [tuigreet](https://github.com/apognu/tuigreet)
- [systemd](https://github.com/systemd/systemd) (init system, login manager and user services used for greetd, idle/lock, snapper, timers, etc.)
- [wlogout](https://github.com/ArtsyMacaw/wlogout) (Power tool for waybar)
- [waybar](https://github.com/Alexays/Waybar) (Status bar with MangoWM)
- [mangown](https://github.com/mangowm/mango) (Windows compositor)

---

## Zsh configuration

The Zsh configuration (`.zshrc`) is kept intentionally minimal and fast, while providing a modern shell experience.

Main features:

- Clean history settings (shared, deduplicated, trimmed) with a large history size
- Completion system using `compinit`, cached in `~/.cache/zsh`, with case-insensitive matching and colored completions
- Fastfetch banner on interactive shell startup if available
- Plugin setup without a plugin manager:
  - `zsh-autosuggestions`
  - `fast-syntax-highlighting`
  - `fzf-tab`
- Prompt powered by `starship` with config in `~/.config/starship.toml`
- Incremental history search via `zsh-history-substring-search` (up/down arrows)
- Tight integration with `fzf` and `zoxide`:
  - Custom `FZF_DEFAULT_COMMAND` and previews using `bat`
  - Key bindings and completion from the system `fzf` scripts
- Convenient aliases:
  - Navigation (`..`, `...`, `....`)
  - Tools (`b` for yazi, `n` for neovim)
  - Git shortcuts (`g`, `gs`, `ga`, `gc`, `gp`, `gl`)
  - `eza` replacing `ls` with different presets
  - `rg` as default grep-like search
- OSINT helpers:
  - `whois-ip`, `geoip`, `myip`, `headers`, `dns`, `subdomains`, `shot`, `topcmd`
- Arch Linux workflow:
  - `pacman` and `yay` aliases for install, upgrade, cleanup, orphan handling
  - `journalctl` aliases (`jlog`, `jfollow`, `jboot`)
- Utility functions:
  - `extract` for unpacking many archive formats
  - `mkcd` to create and enter a directory
  - `psgrep` to search running processes
- Python / pyenv helpers:
  - pyenv initialization
  - `va` to activate `venv/` or `.venv/`
  - aliases for creating, destroying and managing virtualenvs and `requirements.txt`

---

## Themes: `.themes/Catppuccin-Mocha`

This directory contains the Catppuccin Mocha theme adapted for several environments:

- `cinnamon/`  
  Cinnamon desktop theme, including CSS and assets like checkboxes, toggles and window control icons.
- `gnome-shell/`  
  GNOME Shell theme with CSS files and SVG assets for shell elements (calendar, toggles, process animation).
- `gtk-2.0/`, `gtk-3.0/`, `gtk-4.0/`  
  GTK themes for legacy and modern GTK applications, including:
  - `gtkrc` and `gtkrc.hidpi` for GTK2
  - `gtk.css` and `gtk-dark.css` plus a large set of SVG assets for GTK3/4 widgets (checkboxes, radio buttons, sliders, etc.).
- `metacity-1/`  
  Window manager theme for Metacity-based environments.
- `plank/`  
  Theme for the Plank dock (`dock.theme`).
- `xfwm4/`  
  Theme configuration for XFWM4 window manager.
- `index.theme`  
  The theme index file used by the system to register Catppuccin Mocha.

This ensures a consistent Catppuccin Mocha look across desktops, apps and widgets.

---

## Yazi: `.config/yazi`

<p align="center">
    <img src=https:https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/yazi.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

Configuration for the Yazi terminal file manager:

- `yazi.toml`  
  Main Yazi configuration.
- `theme.toml`  
  Custom Yazi theme to match the overall colors.
- `keymap.toml`  
  Custom key mappings for navigation and actions.
- `package.toml`  
  Package metadata for the configuration.

---

## Wofi: `.config/wofi`

Configuration for Wofi, a Wayland application launcher and cliphist manager:

- `config`  
  Main Wofi settings (mode, matching, behavior).
- `style.css`  
  CSS styling to match the Catppuccin-like look.
- `wifi`  
  Script or configuration used to manage Wi-Fi selection via Wofi.

---

## Starship: `.config/starship.toml`

<p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/starship.jpg width="600" alt="screenshot">
    </img>
</p>

Prompt configuration for the Starship prompt, referenced from `.zshrc`.  
It defines the segments, colors and layout of the prompt to integrate visually with the rest of the setup.

---

## Sway: `.config/sway`

Sway configuration is split into multiple modular files for clarity:

- `config`  
  Main Sway configuration file that typically includes the others.
- `autostart.conf`  
  Applications and services launched automatically when Sway starts.
- `bar.conf`  
  Status bar configuration, including integration with `i3status-rust`.
- `bind.conf`  
  Keybindings for window management, launching applications, workspaces, etc.
- `input.conf`  
  Input configuration (keyboard, touchpad, etc.).
- `rules.conf`  
  Window rules (floating windows, specific workspaces, etc.).
- `style.conf`, `swayfx.conf`, `tty-style.conf`  
  Visual tweaks, SwayFX configuration and TTY-like styling.
- `catppuccin-mocha`  
  Theme-related configuration for Sway using the Catppuccin Mocha palette.
- `i3status.toml`  
  Configuration file for `i3status-rust` used in the bar.
- `assets/screen.jpg`  
  Screenshot or background asset.
- `scripts/`  
  Helper scripts:
  - `copypast` to integrate clipboard history with Wofi and images
  - `inactive-windows-transparency.py` for window transparency effects
- `README.md`  
  Local documentation for the Sway setup.

---

## Qt: `.config/qt5ct` and `.config/qt6ct`

Qt theming configuration using `qt5ct` and `qt6ct`:

- `colors/catppuccin-mocha-lavender.conf`  
  Qt colour scheme matching the Catppuccin Mocha palette.
- `qss/`  
  Extra styling via Qt Style Sheets.
- `qt5ct.conf`, `qt6ct.conf`  
  Main Qt configuration files for both Qt5 and Qt6, aligning fonts, colors and style.

---

## Neovim: `.config/nvim`

<p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/nvim.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

Neovim configuration built in Lua with a modern plugin stack:

- `init.lua`  
  Entry point that sets up Neovim and loads modules.
- `lua/config/`  
  Core configuration:
  - `lazy.lua` for the Lazy plugin manager
  - `maps.lua` for key mappings
  - `markdown.lua` for markdown-related settings
- `lua/plugins/`  
  Plugin configuration files, one per plugin or group:
  - `bufferline.lua`
  - `catppuccin.lua`
  - `cmp.lua`
  - `colorscheme.lua`
  - `filebrowser.lua`
  - `gitsign.lua`
  - `lsp.lua`
  - `mini-icons.lua`
  - `mini_map.lua`
  - `neowiki.lua`
  - `nvim-autopair.lua`
  - `outline.lua`
  - `render-markdown.lua`
  - `starter.lua`
  - `neo-tree.lua`
  - `telescope.lua`
  - `treesitter.lua`
  - `ui.lua`
  - `vim-fugitive.lua`
  - `witch-key.lua` (which-key style helper)
  - `nvim-tree.lua.old` (old configuration kept for reference)
- `lazy-lock.json`  
  Lockfile for Lazy to pin exact plugin versions.
- `assets/`  
  Screenshots and images for documentation (`nvim-starter.*`, `screen.jpg`).
- `LICENSE.md`, `readme.md`  
  Local documentation and license for the Neovim configuration.

This setup gives a modern, IDE-like Neovim experience with LSP, Treesitter, file browsing, git integration, markdown rendering and more.

---

## Kitty: `.config/kitty`

Kitty terminal configuration and themes:

<p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/kitty.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

- `kitty.conf`  
  Main Kitty configuration (fonts, window behavior, keybindings, etc.).
- `current-theme.conf`  
  Includes or defines the currently active theme.
- `kitty-themes/`  
  A full copy of the kitty-themes collection:
  - `LICENSE.md`, `README.md`, `CONTRIBUTING.md`
  - `themes/*.conf`  
    Hundreds of ready-to-use color schemes (Solarized, Dracula, Gruvbox, Monokai variants, Catppuccin-like themes, etc.).

This allows instant switching between many color schemes while defaulting to a Catppuccin-style dark theme.

---

## Snapper

Snapper is used here to manage Btrfs snapshots for the root filesystem.
Its main configuration for this setup lives in /etc/snapper/configs/root, where snapshot limits and cleanup rules are defined.
Together with grub-btrfs, this configuration is integrated into GRUB so that the created snapshots appear as additional boot entries in the GRUB menu and can be selected directly at startup.

---

## wiki
This wiki is my personal cybersecurity knowledge base.
It centralizes course notes, lab write‑ups and reference material for networking, blue team and red team topics, so I can grow a coherent skill set over time instead of scattered notes.
The structure is intentionally simple: foundations first, then focused sections for tools and defensive/offensive techniques, plus dedicated reference indexes to quickly jump back to key resources when needed.

All my notes live in a Neovim‑driven wiki.
From a terminal session, I just launch: 
```shell
nvim
``` 
and use 
```
<leader>ww
```
to open my main index page, then navigate through Markdown links like a lightweight personal documentation site.

---

## Other configs

Additional directories complete the environment:

- `.config/i3status-rust/`  
  Used by the Sway bar via `i3status.toml` (config content is referenced from Sway’s side).
 <p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/i3s.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

- `.config/gtk-3.0/` and `.config/gtk-4.0/`  
  GTK settings and overrides for applications using GTK3/GTK4 (bookmarks, settings backups, etc.).
- `.config/fastfetch/config.jsonc`  
  Fastfetch configuration controlling system summary display in the terminal.
  <p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/fastfetch.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

- `.config/eza/catppuccin-mocha-lavender.yml`  
  eza color theme file tuned to match Catppuccin Mocha.
 <p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/eza.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

- `.config/cliphist/config`  
  Configuration for cliphist clipboard manager.
- `.config/calcure/`  
  Calcure TUI calendar and task manager configuration:
  - `config.ini`
  - `events.csv`
  - `tasks.csv`
  - `info.log`
- `.config/bat/themes/Catppuccin Mocha.tmTheme`  
  Bat syntax highlighting theme, again using Catppuccin Mocha.
 <p align="center">
    <img src=https://git.labfytools.com/fy59/Dotfiles_ArchAP/raw/branch/main/.assets/bat.jpg width="600" height="400" alt="screenshot">
    </img>
</p>

---

## Installation (on existing system)

### YAY install

```shell
sudo pacman -S stow git base-devel
cd /tmp
git clone https://aur.archlinux.org/yay.git
cd yay
makepkg -si
```

### Git clone & themes install

```shell
yay -S catppuccin-cursors-mocha catppuccin-gtk-theme-mocha && git clone https://github.com/grayTerminal-sh/archasp.git
```

### Move dotfiles

```shell
mkdir ~/.dotfiles &&\
mv ~/archasp/* ~/.dotfiles &&\
rm -r ~/archasp
```

### Config backup

```shell
cd &&\
mkdir ~/.config/config_backup &&\
mv ~/.config/atuin ~/.config/config_backup &&\
mv ~/.config/bat ~/.config/config_backup &&\
mv ~/.config/btop ~/.config/config_backup &&\
mv ~/.config/calcure ~/.config/config_backup &&\
mv ~/.config/cliphist ~/.config/config_backup &&\
mv ~/.config/eza ~/.config/config_backup &&\
mv ~/.config/fastfetch ~/.config/config_backup &&\
mv ~/.config/gtk-3.0 ~/.config/config_backup &&\
mv ~/.config/gtk-4.O ~/.config/config_backup &&\
mv ~/.config/icons ~/.config/config_backup &&\
mv ~/.config/kitty ~/.config/config_backup &&\
mv ~/.config/mango ~/.config/mango_backup &&\
mv ~/.config/nvim ~/.config/config_backup &&\
mv ~/.config/qt5ct ~/.config/config_backup &&\
mv ~/.config/qt6ct ~/.config/config_backup &&\
mv ~/.config/starship ~/.config/config_backup &&\
mv ~/.config/sway ~/.config/config_backup &&\
mv ~/.config/swaylock ~/.config/config_backup &&\
mv ~/.config/swaync ~/.config/config_backup &&\ 
mv ~/.config/themes ~/.config/config_backup &&\
mv ~/.config/wofi ~/.config/config_backup &&\
mv ~/.config/yazi ~/.config/config_backup &&\
mv ~/.config/zsh ~/.config/config_backup
```

### Stow dotfiles & install packages

```shell
cd ~/.dotfiles
```

```shell
stow *\
```

```shell
yay -S \
  mangowm-git swayfx wofi i3status-rust kitty neovim zsh \
  starship fzf fd ripgrep eza fastfetch yazi bat \
  cliphist calcure zoxide pyenv git \
  gtk3 gtk4 catppuccin-gtk-theme-mocha \
  catppuccin-cursors-mocha swaylock-effects \
  swayidle greetd greetd-tuigreet grim slurp \
  snapper brtfs-progs grub-snapper uwsm
```

### greetd-tuigreet config

---

```toml
# /etc/greetd/config.toml

[terminal]
# The VT to run the greeter on. Can be "next", "current" or a number
# designating the VT.
vt = 1

# The default session, also known as the greeter.
[default_session]
command = "tuigreet tuigreet --time --greeting 'Welcome to ArchASP' --theme 'container=brightblack;border=magenta;text=white;greet=brightmagenta;prompt=cyan;input=brightcyan;time=brightyellow;error=red;button=green;action=green' --cmd 'uwsm start default' --power-shutdown 'shutdown -h now' --power-reboot 'reboot'"

# The user to run the command as. The privileges this user must have depends
# on the greeter. A graphical greeter may for example require the user to be
# in the `video` group.
user = "greetd"

```

---

```desktop
# /usr/share/wayland-sessions/mango.desktop

[Desktop Entry]
Encoding=UTF-8
Name=Mango
DesktopNames=mango;wlroots
Comment=mango WM
Exec=mango
Icon=mango
Type=Application

```

---

```sh
#!/bin/sh

# .local/bin/mango-session.sh

systemctl --user start wayland-session.target
exec mango
```

---

```shell
sudo systemctl enable --now greetd.service
```

### Snapper config

```shell
sudo snapper -c root create-config /\
sudo snapper -c root create-config /@
```

```shell
sudo systemctl enable --now grub-btrfsd.service grub-btrfs.path
```

```shell
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

```config
# /etc/snapper/configs/root
# subvolume to snapshot
SUBVOLUME="/"

# filesystem type
FSTYPE="btrfs"


# btrfs qgroup for space aware cleanup algorithms
QGROUP=""


# fraction or absolute size of the filesystems space the snapshots may use
SPACE_LIMIT="0.5"

# fraction or absolute size of the filesystems space that should be free
FREE_LIMIT="0.2"


# users and groups allowed to work with config
ALLOW_USERS=""
ALLOW_GROUPS=""

# sync users and groups from ALLOW_USERS and ALLOW_GROUPS to .snapshots
# directory
SYNC_ACL="no"


# start comparing pre- and post-snapshot in background after creating
# post-snapshot
BACKGROUND_COMPARISON="yes"


# run daily number cleanup
NUMBER_CLEANUP="yes"

# limit for number cleanup
NUMBER_MIN_AGE="3600"
NUMBER_LIMIT="5"
NUMBER_LIMIT_IMPORTANT="1"


# create hourly snapshots
TIMELINE_CREATE="yes"

# cleanup hourly snapshots after some time
TIMELINE_CLEANUP="yes"

# limits for timeline cleanup
TIMELINE_MIN_AGE="3600"
TIMELINE_LIMIT_HOURLY="0"
TIMELINE_LIMIT_DAILY="3"
TIMELINE_LIMIT_WEEKLY="0"
TIMELINE_LIMIT_MONTHLY="0"
TIMELINE_LIMIT_QUARTERLY="0"
TIMELINE_LIMIT_YEARLY="0"


# cleanup empty pre-post-pairs
EMPTY_PRE_POST_CLEANUP="yes"

# limits for empty pre-post-pair cleanup
EMPTY_PRE_POST_MIN_AGE="3600"
```
