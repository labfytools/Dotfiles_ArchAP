#!/usr/bin/python3
"""Capture only requested Sway toplevels, on demand for the dock hover panel.

Privacy: 0700 XDG_RUNTIME_DIR cache; no full-desktop capture, no permanent
storage, bounded captures, and no Wayland focus/activation commands.
"""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

WINDOW_ID = re.compile(r"^[1-9][0-9]{0,18}$")
FOREIGN_ID = re.compile(r"^[a-f0-9]{32}$")
ROOT_NAME = "labfy-dock-window-thumbnails"
MAX_IMAGES = 8
MAX_PNG_BYTES = 2_000_000
MAX_ARGUMENT = 2048
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def cache_root():
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    if not runtime.is_dir() or runtime.is_symlink() or runtime.stat().st_uid != os.getuid():
        raise ValueError("XDG_RUNTIME_DIR invalide")
    root = runtime / ROOT_NAME
    if root.is_symlink():
        raise ValueError("Cache de vignettes invalide")
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError("Permissions du cache de vignettes invalides")
    return root


def purge(root, *, all_dirs=False):
    for entry in root.iterdir():
        if not entry.name.startswith("shot-") or entry.is_symlink() or not entry.is_dir():
            continue
        try:
            info = entry.stat()
            if info.st_uid == os.getuid() and (all_dirs or time.time() - info.st_mtime > 120):
                shutil.rmtree(entry)
        except OSError:
            pass


def validate(raw):
    if not isinstance(raw, str) or len(raw) > MAX_ARGUMENT:
        raise ValueError("Demande de vignettes invalide")
    rows = json.loads(raw)
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_IMAGES:
        raise ValueError("Nombre de vignettes invalide")
    result = []
    ids, foreign = set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "foreignId"}:
            raise ValueError("Donnée de fenêtre invalide")
        wid, fid = row["id"], row["foreignId"]
        if (not isinstance(wid, str) or WINDOW_ID.fullmatch(wid) is None
                or not isinstance(fid, str) or FOREIGN_ID.fullmatch(fid) is None
                or wid in ids or fid in foreign):
            raise ValueError("Identifiant de fenêtre invalide")
        ids.add(wid)
        foreign.add(fid)
        result.append((wid, fid))
    return result


def capture(raw, *, tool=None):
    selected = validate(raw)
    root = cache_root()
    purge(root)
    folder = Path(tempfile.mkdtemp(prefix="shot-", dir=root))
    output = {}
    tool = tool or str(Path.home() / ".local/libexec/labfy-wlthumbs")
    try:
        completed = subprocess.run(
            [tool, "-ids", ",".join(fid for _, fid in selected),
             "-size", "224", "-dir", str(folder)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=6, check=False)
        if completed.returncode != 0:
            return {"images": {}, "error": "Capture indisponible"}
        for wid, fid in selected:
            path = folder / (fid + ".png")
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                    continue
                if not 8 < info.st_size < MAX_PNG_BYTES:
                    continue
                with path.open("rb") as stream:
                    if stream.read(8) != PNG_MAGIC:
                        continue
                output[wid] = path.as_uri()
            except OSError:
                continue
        return {"images": output, "error": ""}
    except (OSError, subprocess.TimeoutExpired):
        return {"images": {}, "error": "Capture indisponible"}
    finally:
        if not output:
            shutil.rmtree(folder, ignore_errors=True)


def main(argv):
    try:
        if len(argv) == 1 and argv[0] == "clear":
            purge(cache_root(), all_dirs=True)
            return 0
        if len(argv) != 2 or argv[0] != "capture":
            raise ValueError("Commande invalide")
        result = capture(argv[1])
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print(json.dumps({"images": {}, "error": "Capture indisponible"}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
