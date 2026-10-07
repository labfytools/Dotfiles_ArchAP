#!/bin/sh
# Vérifie le démarrage Sway + GTK installés comme greeter, sans VT ni login réel.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Exécuter comme root' >&2; exit 1; }
runtime=$(mktemp -d)
chown greeter:greeter "$runtime"
chmod 0700 "$runtime"
set +e
timeout --signal=TERM --kill-after=2s 10s \
    runuser -u greeter -- env XDG_RUNTIME_DIR="$runtime" \
    WLR_BACKENDS=headless WLR_RENDERER=pixman GREETD_SOCK="$runtime/unused" \
    /usr/local/libexec/labfy-greeter/start-compositor >"$runtime/smoke.log" 2>&1 &
runner=$!
sleep 3
if pgrep -u greeter -f '^/usr/bin/python3 /usr/local/libexec/labfy-greeter/labfy_greeter.py$' >/dev/null; then
    gtk_started=yes
else
    gtk_started=no
fi
wait "$runner"
result=$?
set -e
if [ "$gtk_started" = yes ] && { [ "$result" -eq 124 ] || [ "$result" -eq 137 ]; } && \
    ! pgrep -u greeter -f '^/usr/bin/python3 /usr/local/libexec/labfy-greeter/labfy_greeter.py$' >/dev/null; then
    echo 'HEADLESS_GREETER_SMOKE=PASS (GTK actif, arrêt contrôlé, aucun processus résiduel)'
else
    cat "$runtime/smoke.log" >&2
    echo "HEADLESS_GREETER_SMOKE=FAIL gtk=$gtk_started exit=$result" >&2
    rm -rf -- "$runtime"
    exit 1
fi
rm -rf -- "$runtime"
