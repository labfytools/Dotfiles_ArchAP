#!/usr/bin/python3
"""Construire les candidats locaux, sans installer ni signer ni accéder au réseau."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "quickshell/.config/quickshell/labfy-sway"


def build(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT): raise ValueError("OUTPUT_MUST_BE_IN_ISOLATED_WORKTREE")
    output.mkdir(parents=True, exist_ok=True)
    binary = output / "labfy-v2-anchor"
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "gtk+-3.0", "gdk-wayland-3.0"], text=True).split()
    subprocess.run(["cc", "-std=c17", "-O2", "-Wall", "-Wextra", "-Werror", str(SOURCE / "session_v2/anchor_helper.c"), "-o", str(binary), *flags], check=True)
    xpi = output / "labfy-session-v2-unsigned.xpi"
    with zipfile.ZipFile(xpi, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest.json", "background.js"):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (ROOT / "firefox-extension/session-v2" / name).read_bytes())
    bundle = output / "labfy-session-v2-backend.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name in ("session-v2.py", "session-v2-native-host.py"):
            archive.add(SOURCE / name, arcname=name)
        for p in sorted((SOURCE / "session_v2").glob("*.py")): archive.add(p, arcname="session_v2/" + p.name)
        archive.add(SOURCE / "session_v2/schema-v1.json", arcname="session_v2/schema-v1.json")
        archive.add(binary, arcname="session_v2/libexec/labfy-v2-anchor")
        archive.add(ROOT / "firefox-extension/session-v2/native-host.json.in", arcname="native-host.json.in")
    manifest = {"signed": False, "installed": False, "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (binary, xpi, bundle)}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__": build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build/session-v2")
