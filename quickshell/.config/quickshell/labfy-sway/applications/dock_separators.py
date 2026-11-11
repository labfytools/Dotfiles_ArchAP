"""Strict, independent dock separators persisted alongside shared favorites.

Separators are *not* desktop applications; the favorites v1 schema remains
unchanged. Positions denote gaps in the current ordered pinned-app list.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

MAX_SEPARATORS = 16
MAX_BYTES = 4096
SEPARATOR_ID = re.compile(r"^sep-[a-f0-9]{12}$")


def path_for(favorites_path):
    return Path(favorites_path).with_name("dock-separators.json")


def _position(value):
    return type(value) is int and 0 <= value <= 64


def read(path):
    try:
        if path.is_symlink():
            raise ValueError("État des séparateurs invalide")
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return []
    if len(raw) > MAX_BYTES:
        raise ValueError("État des séparateurs trop volumineux")
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("État des séparateurs invalide") from exc
    entries = data.get("separators") if isinstance(data, dict) and data.get("version") == 1 else None
    if (not isinstance(entries, list) or len(entries) > MAX_SEPARATORS
            or any(not isinstance(e, dict) or set(e) != {"id", "position"}
                   or not isinstance(e["id"], str)
                   or SEPARATOR_ID.fullmatch(e["id"]) is None
                   or not _position(e["position"]) for e in entries)):
        raise ValueError("État des séparateurs invalide")
    if (len({e["id"] for e in entries}) != len(entries)
            or len({e["position"] for e in entries}) != len(entries)):
        raise ValueError("Séparateurs dupliqués")
    return entries


def write(path, action, values):
    """One atomic move/add/remove; never replace a possibly stale full list."""
    if action not in ("add", "remove", "move") or not isinstance(values, list):
        raise ValueError("Action de séparateur invalide")
    if action == "add" and (len(values) != 1 or not _position(values[0])):
        raise ValueError("Position de séparateur invalide")
    if action == "remove" and (len(values) != 1 or not isinstance(values[0], str)
                               or SEPARATOR_ID.fullmatch(values[0]) is None):
        raise ValueError("Identifiant de séparateur invalide")
    if action == "move" and (len(values) != 2 or not isinstance(values[0], str)
                             or SEPARATOR_ID.fullmatch(values[0]) is None
                             or not _position(values[1])):
        raise ValueError("Déplacement de séparateur invalide")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        entries = read(path)
        if action == "add":
            pos = values[0]
            if len(entries) >= MAX_SEPARATORS:
                raise ValueError("Trop de séparateurs")
            if any(e["position"] == pos for e in entries):
                raise ValueError("Un séparateur existe déjà ici")
            used = {e["id"] for e in entries}
            identifier = "sep-" + secrets.token_hex(6)
            while identifier in used:
                identifier = "sep-" + secrets.token_hex(6)
            entries.append({"id": identifier, "position": pos})
        elif action == "remove":
            if not any(e["id"] == values[0] for e in entries):
                raise ValueError("Séparateur indisponible")
            entries = [e for e in entries if e["id"] != values[0]]
        else:
            identifier, pos = values
            entry = next((e for e in entries if e["id"] == identifier), None)
            if entry is None:
                raise ValueError("Séparateur indisponible")
            if any(e["id"] != identifier and e["position"] == pos for e in entries):
                raise ValueError("Un séparateur existe déjà ici")
            entry["position"] = pos
        entries.sort(key=lambda e: (e["position"], e["id"]))
        payload = (json.dumps({"version": 1, "separators": entries},
                              ensure_ascii=False) + "\n").encode("utf-8")
        fd, temporary = tempfile.mkstemp(prefix=".dock-separators-", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            os.fsync(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return entries
    finally:
        os.close(directory)
