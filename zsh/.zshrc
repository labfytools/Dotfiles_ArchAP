# =========================
# Zsh clean config
# =========================

# Interactive only
[[ -o interactive ]] || return

# =========================
# PATH & env
# =========================
# Un seul exemplaire de chaque chemin, y compris après pyenv.
typeset -U path
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="$HOME/.local/npm/bin:$PATH"
export PYENV_ROOT="$HOME/.pyenv"
export HISTFILE="$HOME/.zsh_history"
export HISTSIZE=10000
export SAVEHIST=10000
export EDITOR=/usr/bin/nvim
export VISUAL=/usr/bin/nvim
export SYSTEMD_EDITOR=nvim
export SUDO_EDITOR=/usr/bin/nvim
export GPG_TTY=$(tty)

# =========================
# History
# =========================
setopt APPEND_HISTORY
setopt SHARE_HISTORY
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_REDUCE_BLANKS
setopt HIST_FIND_NO_DUPS
bindkey '^[[A' history-beginning-search-backward
bindkey '^[[B' history-beginning-search-forward

# =========================
# Basic behavior
# =========================
setopt AUTO_CD
setopt EXTENDED_GLOB
setopt NO_MATCH
unsetopt BEEP
bindkey '^[[3~' delete-char

# =========================
# Completion system
# =========================
fpath=("$HOME/.zsh/completions" $fpath)

autoload -Uz compinit
# Dump persistant des complétions, sous le cache XDG.
ZSH_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/zsh"
if [[ -d "$ZSH_CACHE_DIR" ]] || command mkdir -p -m 700 -- "$ZSH_CACHE_DIR"; then
    compinit -d "$ZSH_CACHE_DIR/zcompdump"
else
    compinit
fi

zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}
zstyle ':completion:*' menu no
zstyle ':completion:*' use-cache on
zstyle ':completion:*' cache-path ~/.cache/zsh/zcompcache

# =========================
# Fastfetch
# =========================

# Afficher fastfetch à l'ouverture d'un shell interactif
if command -v fastfetch >/dev/null 2>&1; then
    fastfetch
fi

# =========================
# Plugins sans zinit
#   (à cloner une fois pour toutes dans ~/.zsh/plugins/)
#   git clone https://github.com/zsh-users/zsh-autosuggestions.git
#   git clone https://github.com/zdharma-continuum/fast-syntax-highlighting.git
#   git clone https://github.com/Aloxaf/fzf-tab.git
# =========================
source ~/.zsh/catppuccin_mocha-zsh-syntax-highlighting.zsh

if [ -d "$HOME/.zsh/plugins" ]; then
    [ -r "$HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh" ] &&
        source "$HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh"

    [ -r "$HOME/.zsh/plugins/fast-syntax-highlighting/fast-syntax-highlighting.plugin.zsh" ] &&
        source "$HOME/.zsh/plugins/fast-syntax-highlighting/fast-syntax-highlighting.plugin.zsh"

    [ -r "$HOME/.zsh/plugins/fzf-tab/fzf-tab.zsh" ] &&
        source "$HOME/.zsh/plugins/fzf-tab/fzf-tab.zsh"
fi

zstyle ':completion:*' menu select

# =========================
# Starship prompt
# =========================
export STARSHIP_CONFIG="$HOME/.config/starship.toml"
command -v starship >/dev/null && eval "$(starship init zsh)"

# =========================
# FZF + zoxide + Atuin
# =========================
# CONTRAT: fd produit les chemins; FZF_DEFAULT_OPTS contient uniquement les options UI.
export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'
# Ctrl+R appartient a Atuin, Ctrl+F reste disponible pour l'historique FZF.
export FZF_CTRL_R_COMMAND=''
export FZF_DEFAULT_OPTS="
    --height=30%
    --layout=reverse
    --border
    --preview 'bat --style=numbers --color=always --line-range=:200 {}'
    --preview-window=right:50%
    --color=bg+:#313244,bg:#1E1E2E,spinner:#F5E0DC,hl:#F38BA8 \
    --color=fg:#CDD6F4,header:#F38BA8,info:#CBA6F7,pointer:#F5E0DC \
    --color=marker:#B4BEFE,fg+:#CDD6F4,prompt:#CBA6F7,hl+:#F38BA8 \
    --color=selected-bg:#45475A \
    --color=border:#6C7086,label:#CDD6F4
"

# Le chargeur fzf --zsh fournit deja ces deux integrations.

command -v fzf >/dev/null && eval "$(fzf --zsh)"
command -v zoxide >/dev/null && eval "$(zoxide init zsh)"
# Atuin installe ses bindings apres FZF : Ctrl+R reste reserve a Atuin.
command -v atuin >/dev/null && eval "$(atuin init zsh)"

# =========================
# Aliases de base
# =========================
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'

# Tools
alias b='yazi'
alias n='nvim'

# Git
# Ne jamais enchaîner automatiquement staging, commit et push.
alias g='git status --short'
alias gs='git status'
alias ga='git add .'
gc() {
    echo -n "Message de commit: "
    read msg
    git commit -m "$msg"
}
gp() {
    local branch target
    branch="$(git branch --show-current)" || return 1
    if [[ -z "$branch" ]]; then
        print -u2 "Erreur : aucune branche Git active."
        return 1
    fi
    # URL de fetch : une destination unique, même si origin déclare plusieurs pushurl.
    target="$(git remote get-url origin)" || return 1
    print -r -- "Push vers une seule destination : $target ($branch)"
    git push "$target" "$branch"
}
alias gl='git log --oneline --graph --decorate'
gpall() {
    local branch answer
    branch="$(git branch --show-current)" || return 1
    if [[ -z "$branch" ]]; then
        print -u2 "Erreur : aucune branche Git active."
        return 1
    fi
    print 'Destinations de publication configurees pour origin :'
    git remote get-url --push --all origin || return 1
    read -r 'answer?Confirmer le push sur TOUTES ces destinations (taper OUI) : ' || return 1
    if [[ "$answer" != 'OUI' ]]; then
        print 'Publication annulee.'
        return 1
    fi
    git push origin "$branch"
}
# Grep / ripgrep
alias grep='grep --color=auto'
alias rg='rg --hidden --smart-case'

# Eza
command -v eza >/dev/null && alias ls='eza'
alias ll='eza -lha --git'
alias la='eza -la'
alias lt='eza -T'

# =========================
# OSINT shortcuts
# =========================

alias whois-ip='whois'
geoip() {
    if (( $# != 1 )); then
        print -u2 -- "Usage : geoip <adresse IP>"
        return 2
    fi
    setopt localoptions pipefail
    command curl -fsS --max-time 10 -- "https://ipapi.co/$1/json/" | command jq .
}
alias myip='curl -s ifconfig.me'
alias headers='curl -sI'
alias dns='dig'
subdomains() {
    if (( $# != 1 )); then
        print -u2 -- "Usage : subdomains <domaine>"
        return 2
    fi
    if ! command -v subfinder >/dev/null 2>&1; then
        print -u2 -- "subfinder est absent : installer cet outil avant l'énumération."
        return 127
    fi
    command subfinder -d "$1"
}

alias topcmd="history | awk '{print \$2}' | sort | uniq -c | sort -rn | head -20"
# Wayland natif : capture complète ou sélection rectangulaire.
shot() {
    local mode="${1:-full}" target geometry
    if (( $# > 1 )) || [[ "$mode" != full && "$mode" != region ]]; then
        print -u2 -- "Usage : shot [full|region]"
        return 2
    fi
    target="$HOME/Pictures/osint_$(date +%Y%m%d_%H%M%S_%N).png"
    if [[ "$mode" == region ]]; then
        geometry="$(command slurp)" || return 1
        [[ -n "$geometry" ]] || return 1
        command grim -g "$geometry" "$target" || return $?
    else
        command grim "$target" || return $?
    fi
    print -r -- "$target"
}

# =========================
# Arch workflow
# =========================

alias p='sudo pacman'
alias pS='sudo pacman -S'
alias pR='sudo pacman -Rns'
alias pQ='pacman -Q'
alias pSs='pacman -Ss'
alias pSyu='sudo pacman -Syu'
orphans() {
    local -a pkgs
    # Transformer la liste multiligne de pacman en vrai tableau Zsh.
    pkgs=( ${(f)"$(pacman -Qtdq 2>/dev/null)"} )
    if (( ${#pkgs[@]} == 0 )); then
        print -- "Aucun paquet orphelin"
        return 0
    fi
    print -r -- "Paquets orphelins : ${(j:, :)pkgs}"
    sudo pacman -Rns -- "${pkgs[@]}"
}

update() {
    # Pas de boucle sudo en arrière-plan et pas de -Syyu systématique.
    sudo pacman -Syu || return $?
    aurupdate
}

# =========================
# Keybindings / fzf
# =========================

bindkey '^F' fzf-history-widget

# =========================
# Functions utiles
# =========================

extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.bz2) tar xjf "$1" ;;
            *.tar.gz)  tar xzf "$1" ;;
            *.bz2)     bunzip2 "$1" ;;
            *.rar)     unrar x "$1" ;;
            *.gz)      gunzip "$1" ;;
            *.tar)     tar xf "$1" ;;
            *.tbz2)    tar xjf "$1" ;;
            *.tgz)     tar xzf "$1" ;;
            *.zip)     unzip "$1" ;;
            *.Z)       uncompress "$1" ;;
            *.7z)      7z x "$1" ;;
            *)         echo "'$1' format inconnu" ;;
        esac
    else
        echo "'$1' n'est pas un fichier valide"
    fi
}

mkcd() {
    mkdir -p "$1" && cd "$1"
}

mk() {
    mkdir -p "$1"
}
psgrep() {
    ps aux | grep -v grep | grep -i -e VSZ -e "$@"
}

# =========================
# Python / virtualenv / pyenv
# =========================

export PATH="$PYENV_ROOT/bin:$PATH"
if command -v pyenv >/dev/null; then
    eval "$(pyenv init --path)"
    eval "$(pyenv init -)"
fi

va() {
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
        echo "✅ venv activé"
    elif [[ -f ".venv/bin/activate" ]]; then
        source .venv/bin/activate
        echo "✅ .venv activé"
    else
        echo "❌ Aucun venv trouvé (venv/ ou .venv/)"
        return 1
    fi
};

alias venv='python -m venv venv'
alias vd='deactivate'
# Environnements Python reconnus, avec confirmation obligatoire.
vrm() {
    local -a envs
    local candidate answer
    if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != "--dry-run" ]]; }; then
        print -u2 -- "Usage : vrm [--dry-run]"
        return 2
    fi
    if [[ "$PWD" == "$HOME" || "$PWD" == "/" ]]; then
        print -u2 -- "Refus : lancer vrm dans un répertoire de projet."
        return 1
    fi
    for candidate in venv .venv; do
        if [[ -d "$candidate" && ! -L "$candidate" && -f "$candidate/pyvenv.cfg" ]]; then
            envs+=("$candidate")
        fi
    done
    if (( ${#envs[@]} == 0 )); then
        print -- "Aucun environnement virtuel Python local à retirer."
        return 0
    fi
    print -r -- "Environnements concernés : ${(j:, :)envs}"
    [[ "${1:-}" == "--dry-run" ]] && return 0
    read -r 'answer?Taper SUPPRIMER pour confirmer : ' || return 1
    [[ "$answer" == "SUPPRIMER" ]] || { print -- "Annulé."; return 1; }
    command rm -rf -- "${envs[@]}"
}
alias vreq='pip install -r requirements.txt'
alias vfreeze='pip freeze > requirements.txt'

# =========================
# Python / virtualenv / pyenv
# =========================

# Alias pour la compilation C
alias gcc-debug='gcc -Wall -Wextra -g -std=c17'  
alias gcc-release='gcc -Wall -Wextra -O2 -std=c17'  
alias gcc-strict='gcc -Wall -Wextra -Werror -pedantic -std=c17'  

# Alias pour Valgrind
alias valgrind-check='valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes'

# Nettoyage C : seulement les fichiers ELF exécutables au niveau courant.
clean-exe() {
    local -a binaries
    local candidate answer
    local in_git=0
    command git rev-parse --is-inside-work-tree >/dev/null 2>&1 && in_git=1
    if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != "--dry-run" ]]; }; then
        print -u2 -- "Usage : clean-exe [--dry-run]"
        return 2
    fi
    for candidate in ./*(N.); do
        [[ -x "$candidate" ]] || continue
        command readelf -h -- "$candidate" >/dev/null 2>&1 || continue
        # Ne jamais proposer la suppression d'un binaire suivi par Git.
        if (( in_git )) && command git ls-files --error-unmatch -- "$candidate" >/dev/null 2>&1; then
            continue
        fi
        binaries+=("$candidate")
    done
    if (( ${#binaries[@]} == 0 )); then
        print -- "Aucun exécutable ELF local à retirer."
        return 0
    fi
    print -- "Exécutables ELF candidats (aucune suppression automatique) :"
    printf '  %s\n' "${binaries[@]}"
    [[ "${1:-}" == "--dry-run" ]] && return 0
    read -r 'answer?Taper SUPPRIMER pour confirmer : ' || return 1
    [[ "$answer" == "SUPPRIMER" ]] || { print -- "Annulé."; return 1; }
    command rm -- "${binaries[@]}"
}

# =========================
# Ansible
# =========================

aconfig() {
    local base="$HOME/.ansible"
    local file

    file="$(
        find "$base" -type f 2>/dev/null \
        | fzf --height=80% --layout=reverse --border \
              --prompt="ansible > " \
              --preview 'bat --style=numbers --color=always --line-range=:300 {}'
    )" || return

    [ -n "$file" ] && nvim -c "Neotree left reveal" "$file"
}

# =========================
# Ssh
# =========================

alias ssh-admin='ssh-add ~/.ssh/id_ed25519-admin'

# =========================
# Hyprwhspr 
# =========================
#
alias whon='systemctl --user start hyprwhspr.service'
alias whoff='systemctl --user stop hyprwhspr.service'

# =========================
# Android
# =========================

andromount() {
    local mp="${1:-$HOME/android}"
    mkdir -p "$mp"

    if mount | grep -q "on $mp "; then
        echo "Déjà monté sur $mp"
        return 0
    fi

    echo "Tentative de montage MTP sur $mp..."
    jmtpfs "$mp" && {
        echo "Android monté sur $mp"
        return 0
    }

    echo "Échec du montage."
    echo "Vérifie : téléphone déverrouillé + mode USB = Transfert de fichiers (MTP)."
    return 1
}

# =========================
# Android
# =========================

alias codex-dev='systemd-inhibit --what=sleep:idle --who="codex-dev" --why="Codex development session" --mode=block codex --sandbox workspace-write --ask-for-approval never'
alias codex-hw='systemd-inhibit --what=sleep:idle --who="codex-hw" --why="Codex hardware/Vulkan session" --mode=block codex --sandbox danger-full-access --ask-for-approval never'
alias codex-luna='codex -m gpt-5.6-luna -c model_reasoning_effort=\"low\"'
alias codex-terra='codex -m gpt-5.6-terra -c model_reasoning_effort=\"medium\"'
alias codex-sol='codex -m gpt-5.6-sol -c model_reasoning_effort=\"low\"'

androumount() {
    local mp="${1:-$HOME/android}"
    fusermount -u "$mp" && echo "Android démonté de $mp"
}

# Couleurs pour less / man
export LESS='-R'
export LESS_TERMCAP_mb=$'\e[1;31m'      # blink (rarement utilisé)
export LESS_TERMCAP_md=$'\e[1;34m'      # bold
export LESS_TERMCAP_me=$'\e[0m'        # reset
export LESS_TERMCAP_se=$'\e[0m'        # reset standout
export LESS_TERMCAP_so=$'\e[1;44;33m'  # standout (titres encadrés)
export LESS_TERMCAP_ue=$'\e[0m'        # reset underline
export LESS_TERMCAP_us=$'\e[1;32m'     # underline

# Android SDK
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$PATH:$ANDROID_HOME/platform-tools"

# Dédupliquer réellement le tableau après toutes les initialisations (pyenv inclus).
path=("${path[@]}")
