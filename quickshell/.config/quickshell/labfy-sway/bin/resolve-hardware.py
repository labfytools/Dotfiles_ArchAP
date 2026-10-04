#!/usr/bin/python3
"""Résout les capteurs de cette session sans figer les numéros sysfs."""

from pathlib import Path
import re


DRM = Path("/sys/class/drm")
HWMON = Path("/sys/class/hwmon")


def read(path):
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""


def gpu_busy():
    # INVARIANT: seul un noeud cardN dont l'identité PCI est AMD est retenu.
    for card in sorted(DRM.glob("card[0-9]*")):
        if not re.fullmatch(r"card\d+", card.name):
            continue
        device = card / "device"
        candidate = device / "gpu_busy_percent"
        if read(device / "vendor").lower() == "0x1002" and candidate.is_file():
            return candidate
    return None


def temperature(name, label):
    for monitor in sorted(HWMON.glob("hwmon[0-9]*")):
        if read(monitor / "name") != name:
            continue
        # CONTRACT: préférer le libellé physique ; temp1 sert aux pilotes sans labels.
        inputs = sorted(monitor.glob("temp*_input"))
        for candidate in inputs:
            if read(candidate.with_name(candidate.name.replace("_input", "_label"))).lower() == label:
                return candidate
        fallback = monitor / "temp1_input"
        if fallback.is_file():
            return fallback
    return None


def main():
    # Format fixe sur trois lignes, contrôlé côté QML. Aucun chemin utilisateur.
    for path in (gpu_busy(), temperature("k10temp", "tctl"), temperature("amdgpu", "edge")):
        print(path or "")


if __name__ == "__main__":
    main()
