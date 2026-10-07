#!/bin/sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Exécuter comme root' >&2; exit 1; }
BACKUP=/var/lib/labfy-greeter/backup
( cd "$BACKUP" && sha256sum -c SHA256SUMS )
install -o root -g root -m 0644 "$BACKUP/config.toml" /etc/greetd/config.toml
systemctl daemon-reload
if [ "${1:-}" = --restart ]; then
    systemctl restart greetd.service
fi
echo 'Configuration tuigreet restaurée ; restart uniquement si --restart.'
