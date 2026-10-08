#!/usr/bin/env python3
"""Pont éphémère cliphist : seules les métadonnées et miniatures passent à QML."""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time

IMAGE = re.compile(r"^\[\[ binary data .*?\b(png|jpeg|jpg|bmp|webp)\b", re.I)
MIMES = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "bmp": "image/bmp", "webp": "image/webp"}
MAX_DECODE_BYTES = 256 * 1024 * 1024


def command(db, action):
    return ["cliphist"] + (["-db-path", db] if db else []) + [action]


def entries(db):
    # CONTRACT: les 50 premières lignes sont les plus récentes ; le champ avant TAB est l'identité stable.
    result = subprocess.run(command(db, "list"), capture_output=True, timeout=10)
    if result.returncode:
        if result.returncode == 1 and b"please store something first" in result.stderr:
            return []
        raise RuntimeError("Historique indisponible")
    items = []
    for raw in result.stdout.splitlines()[:50]:
        ident, separator, preview = raw.partition(b"\t")
        if not separator or not ident.isdigit():
            continue
        label = preview.decode("utf-8", "replace")
        image = IMAGE.match(label)
        items.append({"id": ident.decode("ascii"), "image": bool(image),
                      "mime": MIMES.get(image.group(1).lower()) if image else "text/plain;charset=utf-8",
                      "preview": "Image · " + label[3:-3].strip() if image else label[:400]})
    return items


def exact(db, ident):
    if not re.fullmatch(r"[0-9]+", ident):
        raise ValueError("Identifiant invalide")
    for item in entries(db):
        if item["id"] == ident:
            return item
    raise ValueError("Entrée introuvable parmi les 50 éléments affichés")


def decode(db, ident, output):
    # WHY: le flux binaire privé est limité en espace et en temps ; aucune capture mémoire QML.
    process = subprocess.Popen(command(db, "decode"), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    try:
        process.stdin.write((ident + "\t").encode("ascii"))
        process.stdin.close()
        size = 0
        deadline = time.monotonic() + 20
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Décodage trop lent")
                ready = selector.select(max(0, deadline - time.monotonic()))
                if not ready:
                    raise RuntimeError("Décodage trop lent")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DECODE_BYTES:
                    raise RuntimeError("Entrée trop volumineuse")
                output.write(chunk)
        if process.wait(timeout=2):
            raise RuntimeError("Décodage impossible")
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
    output.flush()
    output.seek(0)


def cache_dir():
    # CONTRACT: le test graphique peut isoler les miniatures sans changer le
    # socket Wayland fourni par XDG_RUNTIME_DIR.
    runtime = Path(os.environ.get("LABFY_CLIPHIST_TEST_CACHE_DIR") or
                   os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
    path = runtime / ("labfy-cliphist-panel-" + str(os.getuid()))
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise RuntimeError("Répertoire temporaire non privé")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "select", "delete", "wipe", "thumb", "clean"))
    parser.add_argument("id", nargs="?")
    parser.add_argument("--db-path", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--wl-copy-path", default="wl-copy", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.action == "list":
        print(json.dumps({"items": entries(args.db_path)}, ensure_ascii=False))
    elif args.action == "clean":
        path = cache_dir()
        for file in path.glob("*.png"):
            if file.is_file() and not file.is_symlink():
                file.unlink()
        print('{"ok":true}')
    elif args.action == "wipe":
        # CONTRACT: la confirmation est dans QML ; cette commande n'est appelée qu'après confirmation explicite.
        subprocess.run(command(args.db_path, "wipe"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=10)
        print('{"ok":true}')
    else:
        item = exact(args.db_path, args.id or "")
        if args.action == "delete":
            result = subprocess.run(command(args.db_path, "delete"), input=(item["id"] + "\t").encode("ascii"),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if result.returncode:
                raise RuntimeError("Suppression impossible")
            print('{"ok":true}')
            return
        if args.action == "thumb" and not item["image"]:
            raise ValueError("Miniature réservée aux images")
        with tempfile.TemporaryFile() as decoded:
            decode(args.db_path, item["id"], decoded)
            if args.action == "select":
                # INVARIANT: wl-copy reçoit les octets décodés par stdin avec le MIME exact.
                result = subprocess.run([args.wl_copy_path, "--type", item["mime"]], stdin=decoded,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                if result.returncode:
                    raise RuntimeError("Restauration du presse-papiers impossible")
                print('{"ok":true}')
            else:
                path = cache_dir() / (item["id"] + ".png")
                if not path.exists():
                    with tempfile.NamedTemporaryFile(dir=path.parent, prefix="thumb-", suffix=".png", delete=False) as out:
                        temporary = Path(out.name)
                        try:
                            result = subprocess.run(["magick", "-limit", "memory", "64MiB", "-limit", "map", "128MiB",
                                                     "-limit", "disk", "256MiB", "-limit", "time", "8",
                                                     "-limit", "area", "40MP", "-", "-thumbnail", "180x110>", "png:-"],
                                                    stdin=decoded, stdout=out, stderr=subprocess.DEVNULL, timeout=10)
                            if result.returncode:
                                raise RuntimeError("Miniature indisponible")
                            os.replace(temporary, path)
                        finally:
                            temporary.unlink(missing_ok=True)
                print(json.dumps({"path": path.as_uri()}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError, ValueError) as error:
        # CONTRACT: aucun aperçu ni contenu décodé n'est écrit dans les journaux.
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
