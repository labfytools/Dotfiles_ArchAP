"""État local lu sans privilège et écriture bornée du rétroéclairage."""
from pathlib import Path
import os
import tempfile


def battery(root=Path("/sys/class/power_supply")):
    for path in sorted(root.glob("BAT*")):
        try:
            capacity = int((path / "capacity").read_text().strip())
            status = (path / "status").read_text().strip()
            if 0 <= capacity <= 100:
                return capacity, status
        except (OSError, ValueError):
            continue
    return None


def backlight(root=Path("/sys/class/backlight")):
    for path in sorted(root.iterdir() if root.exists() else []):
        try:
            maximum = int((path / "max_brightness").read_text().strip())
            current = int((path / "brightness").read_text().strip())
            if maximum > 0 and 0 <= current <= maximum:
                return path, maximum, current
        except (OSError, ValueError):
            continue
    return None


def set_brightness(path, maximum, percent):
    if not 10 <= percent <= 100 or maximum <= 0:
        raise ValueError("Luminosité invalide")
    # INVARIANT: jamais zéro ; l'écriture n'est déclenchée qu'à la fin du déplacement du slider.
    value = max(1, round(maximum * percent / 100))
    (path / "brightness").write_text(str(value))


def read_last_user(path=Path("/var/lib/labfy-greeter/state/last-user")):
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value if value and len(value) <= 256 and "\n" not in value else None
    except OSError:
        return None


def save_last_user(username, directory=Path("/var/lib/labfy-greeter/state")):
    if not username or len(username) > 256 or any(ord(c) < 32 for c in username):
        raise ValueError("Nom utilisateur invalide")
    # CONTRACT: seul le nom réussi est publié, par remplacement atomique en mode 0600.
    fd, name = tempfile.mkstemp(prefix=".last-user-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(username + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / "last-user")
    finally:
        if os.path.exists(name):
            os.unlink(name)
