"""Lecture stricte d'une icône AccountsService publiée hors du HOME utilisateur."""
from pathlib import Path
import stat

ICON_ROOT = Path("/var/lib/AccountsService/icons")


def system_icon(username, root=ICON_ROOT):
    # CONTRACT: ne jamais suivre un chemin arbitraire renvoyé par D-Bus ou un
    # alias HOME ; seuls les PNG réguliers root-owned du répertoire système passent.
    if not username or username in (".", "..") or "/" in username or "\\" in username:
        return None
    path = root / username
    try:
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_uid == 0 and 0 < info.st_size <= 2 * 1024 * 1024:
            with path.open("rb") as stream:
                header = stream.read(24)
            if header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR":
                width = int.from_bytes(header[16:20], "big")
                height = int.from_bytes(header[20:24], "big")
                if 0 < width <= 512 and 0 < height <= 512:
                    return path
    except OSError:
        pass
    return None
