#!/bin/sh
# Audit pré-switch en contexte greeter ; aucune action reboot/poweroff n'est exécutée.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Exécuter comme root' >&2; exit 1; }
( cd /var/lib/labfy-greeter/backup && sha256sum -c SHA256SUMS )
for method in CanReboot CanPowerOff; do
    printf '%s=' "$method"
    runuser -u greeter -- /usr/bin/busctl --system call org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager "$method"
done
# CONTRACT: écrire exactement la valeur relue, sans modifier la luminosité visuelle.
runuser -u greeter -- /usr/bin/python3 - <<'PY'
from pathlib import Path
for path in sorted(Path('/sys/class/backlight').glob('*/brightness')):
    value = path.read_text().strip()
    path.write_text(value + '\n')
    if path.read_text().strip() != value:
        raise SystemExit('BRIGHTNESS_PERMISSION=FAIL')
    print('BRIGHTNESS_PERMISSION=PASS device=' + path.parent.name)
    break
else:
    print('BRIGHTNESS_PERMISSION=NO_DEVICE')
PY
