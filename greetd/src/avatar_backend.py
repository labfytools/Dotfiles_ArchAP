#!/usr/bin/python3
"""Publie l'avatar du compte courant via AccountsService, sans privilège local."""
import json
import os
from pathlib import Path
import pwd
import stat
import sys
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError
from avatar_icon import system_icon
import gi
from gi.repository import Gio, GLib

MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS


class AvatarError(Exception):
    pass


def source_path(value):
    """CONTRACT: seule une image locale régulière du compte appelant est acceptée."""
    url = urlsplit(value)
    if url.scheme not in ("", "file") or url.netloc not in ("", "localhost"):
        raise AvatarError("Choisissez un fichier image local.")
    path = Path(unquote(url.path) if url.scheme else value).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SOURCE_BYTES:
        raise AvatarError("L’image doit être un fichier de 12 Mio au maximum.")
    return path


def render_png(source, target):
    """WHY: conversion bornée en PNG carré pour le contrat SetIconFile."""
    try:
        with Image.open(source) as opened:
            if opened.width * opened.height > MAX_SOURCE_PIXELS:
                raise AvatarError("Image trop grande.")
            opened.load()
            normalized = ImageOps.exif_transpose(opened)
            square = ImageOps.fit(normalized.convert("RGBA"), (256, 256), method=Image.Resampling.LANCZOS)
            square.save(target, format="PNG", optimize=True)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise AvatarError("Image illisible ou trop grande.") from exc


def set_avatar(value):
    source = source_path(value)
    username = pwd.getpwuid(os.getuid()).pw_name
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    directory = data_home / "labfy-greeter"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = directory / "avatar.png"
    temporary = directory / f".avatar-{os.getpid()}.png"
    try:
        with temporary.open("xb") as output:
            os.fchmod(output.fileno(), 0o600)
            render_png(source, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        # AccountsService ingère le fichier comme appelant puis publie sa copie root-owned.
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        user_path = bus.call_sync("org.freedesktop.Accounts", "/org/freedesktop/Accounts",
                                  "org.freedesktop.Accounts", "FindUserById",
                                  GLib.Variant("(x)", (os.getuid(),)), GLib.VariantType.new("(o)"),
                                  Gio.DBusCallFlags.NONE, 10000).unpack()[0]
        bus.call_sync("org.freedesktop.Accounts", user_path, "org.freedesktop.Accounts.User",
                      "SetIconFile", GLib.Variant("(s)", (str(destination),)), None,
                      Gio.DBusCallFlags.NONE, 15000)
    finally:
        temporary.unlink(missing_ok=True)
    published = system_icon(username)
    if published is None:
        raise AvatarError("La copie système de l’avatar est indisponible.")
    return str(published)


def main(argv):
    try:
        if argv == ["current"]:
            icon = system_icon(pwd.getpwuid(os.getuid()).pw_name)
            print(json.dumps({"path": str(icon) if icon else ""}))
        elif len(argv) == 2 and argv[0] == "set":
            print(json.dumps({"path": set_avatar(argv[1])}))
        else:
            raise AvatarError("Commande d’avatar invalide.")
    except (AvatarError, OSError, GLib.Error, ValueError) as exc:
        # Les erreurs D-Bus ne sont pas reproduites dans l'interface utilisateur.
        message = str(exc) if isinstance(exc, AvatarError) else "Impossible de modifier l’avatar."
        print(json.dumps({"error": message}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
