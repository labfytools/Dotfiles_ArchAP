"""Namespace distinct de V1 ; noms non interprétés comme chemins."""
import re
from . import schema
from .storage import atomic, private_dir, read, sync_dir, lock
from .errors import require


class Store:
    def __init__(self, root):
        self.root = private_dir(root)
        self.sessions = private_dir(self.root / "sessions")
        self.automatic = private_dir(self.root / "automatic")

    def path(self, name):
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name), "SESSION_NAME_INVALID")
        return self.sessions / (name + ".json")

    def save(self, name, data):
        with lock(self.root, "store.lock"): atomic(self.path(name), data, schema.validate)

    def load(self, name): return read(self.path(name), schema.validate)
    def list(self): return sorted(p.stem for p in self.sessions.glob("*.json") if not p.is_symlink())

    def delete(self, name):
        with lock(self.root, "store.lock"):
            path = self.path(name)
            read(path, schema.validate)
            path.unlink()
            sync_dir(self.sessions)

    def last(self): return read(self.automatic / "last.json", schema.validate)

    def checkpoint(self, data):
        with lock(self.root, "store.lock"): atomic(self.automatic / "last.json", data, schema.validate)
