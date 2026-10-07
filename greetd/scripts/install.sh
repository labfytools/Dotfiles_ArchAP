#!/bin/sh
# Installation préparatoire. Activation explicite uniquement après approbation visuelle.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Exécuter comme root' >&2; exit 1; }
[ "$#" -eq 1 ] && { [ "$1" = --prepare ] || [ "$1" = --activate-after-visual-approval ]; } || { echo 'Usage: install.sh --prepare|--activate-after-visual-approval' >&2; exit 1; }
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKUP=/var/lib/labfy-greeter/backup
install -d -o root -g root -m 0755 /var/lib/labfy-greeter
install -d -o root -g root -m 0700 "$BACKUP"
# CONTRACT: sauvegardes byte-for-byte avant toute écriture sous /etc/greetd.
for file in config.toml sway labfy-sway.conf; do
    if [ -e "/etc/greetd/$file" ] && [ ! -e "$BACKUP/$file" ]; then
        cp -p -- "/etc/greetd/$file" "$BACKUP/$file"
    fi
done
( cd "$BACKUP" && for file in config.toml sway labfy-sway.conf; do
    if [ -f "$file" ]; then sha256sum "$file"; fi
done ) > "$BACKUP/SHA256SUMS"
( cd "$BACKUP" && sha256sum -c SHA256SUMS )
# INVARIANT: seule la configuration d'origine ou notre configuration active
# peut être remplacée. Cela permet de réinstaller le greeter sans accepter
# une modification tierce de /etc/greetd/config.toml.
if ! cmp -s /etc/greetd/config.toml "$BACKUP/config.toml" &&
   ! cmp -s /etc/greetd/config.toml "$SOURCE/config/config.toml"; then
    echo 'Configuration greetd active inconnue depuis la sauvegarde' >&2
    exit 1
fi
install -d -o greeter -g greeter -m 0700 /var/lib/labfy-greeter/config /var/lib/labfy-greeter/state /var/cache/labfy-greeter
install -d -o root -g root -m 0755 /usr/local/libexec/labfy-greeter /usr/local/share/labfy-greeter
for file in labfy_greeter.py greetd_ipc.py auth.py accounts.py system_state.py avatar_icon.py avatar_backend.py; do
    install -o root -g root -m 0644 "$SOURCE/src/$file" "/usr/local/libexec/labfy-greeter/$file"
done
install -o root -g root -m 0755 "$SOURCE/scripts/run-ui" /usr/local/libexec/labfy-greeter/run-ui
install -o root -g root -m 0755 "$SOURCE/scripts/start-compositor" /usr/local/libexec/labfy-greeter/start-compositor
install -o root -g root -m 0755 "$SOURCE/scripts/rollback.sh" /usr/local/libexec/labfy-greeter/rollback
install -o root -g root -m 0644 "$SOURCE/style/labfy-greeter.css" /usr/local/share/labfy-greeter/labfy-greeter.css
install -o root -g root -m 0644 "$SOURCE/config/labfy-sway.conf" /etc/greetd/labfy-sway.conf
# WHY: pkexec nettoie XDG_RUNTIME_DIR ; même --validate exige un répertoire
# runtime possédé par l'appelant. Le backend headless évite de demander un
# siège logind au processus root de validation ; ces variables sont temporaires
# et ne sont jamais transmises au vrai greeter ni à la session UWSM.
validate_dir=$(mktemp -d)
if ! XDG_RUNTIME_DIR="$validate_dir" WLR_BACKENDS=headless WLR_RENDERER=pixman \
    /usr/bin/sway --validate --config /etc/greetd/labfy-sway.conf; then
    rm -rf -- "$validate_dir"
    exit 1
fi
rm -rf -- "$validate_dir"
# Le tty2 est requis comme voie de récupération avant tout basculement.
systemctl enable --now getty@tty2.service
systemctl is-active --quiet getty@tty2.service
if [ "$1" = --prepare ]; then
    echo 'Préparation terminée ; config.toml actif inchangé.'
    exit 0
fi
[ -e "$BACKUP/config.toml" ] || { echo 'Sauvegarde greetd absente' >&2; exit 1; }
install -o root -g root -m 0644 "$SOURCE/config/config.toml" /etc/greetd/config.toml
# INVARIANT: aucun restart greetd ; le changement attend le logout normal.
echo 'Configuration activée sur disque. greetd ne sera pas redémarré.'
