"""Interface provider ; observations runtime privées, vivantes et périssables.

Le moteur ne connaît ni WebExtension ni titrePreface. Le provider exige un mapping
complet du jeu courant de surfaces, avec publisher vivant, puis un arbre stable.
Les fichiers runtime ne sont jamais des identités persistantes du snapshot.
"""
from abc import ABC, abstractmethod
import os
from pathlib import Path
import signal
import time
from .errors import Failure, require
from .schema import UUID, PROVIDER, fields, integer
from .storage import private_dir, read, atomic
from .ipc import until


class IdentityProvider(ABC):
    @abstractmethod
    def available(self): pass
    @abstractmethod
    def capture(self, nodes, timeout=6): pass
    @abstractmethod
    def resolve(self, expected, nodes, timeout=6): pass
    def verify(self, mapping, nodes): return self.capture(nodes) == mapping


def process_start(pid): return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def validate_record(r):
    fields(r, "schema version session uuid con_id observed_ns publisher_pid publisher_start")
    require(r["schema"] == PROVIDER and type(r["version"]) is int and r["version"] == 1, "PROVIDER_RECORD_INVALID")
    require(type(r["uuid"]) is str and UUID.fullmatch(r["uuid"]), "INVALID_UUID")
    for key in ("con_id", "observed_ns", "publisher_pid"): integer(r[key], 1, 2**63 - 1)
    require(type(r["publisher_start"]) is str and r["publisher_start"].isdigit(), "PROVIDER_RECORD_INVALID")
    return r


class FirefoxProvider(IdentityProvider):
    def __init__(self, sway, runtime):
        self.sway = sway
        self.directory = private_dir(Path(runtime) / "session-v2/firefox" / sway.session)

    def available(self):
        for p in list(self.directory.glob("*.json"))[:257]:
            if not p.stem.isdigit(): continue
            try:
                if self._valid(p): return True
            except (OSError, Failure): continue
        return False

    def _valid(self, path):
        r = read(path, validate_record)
        require(r["session"] == self.sway.session and 0 <= time.monotonic_ns() - r["observed_ns"] < 3_000_000_000, "PROVIDER_STALE")
        require(Path(f'/proc/{r["publisher_pid"]}').stat().st_uid == os.getuid(), "PROVIDER_STALE")
        fd = os.pidfd_open(r["publisher_pid"])
        try:
            require(process_start(r["publisher_pid"]) == r["publisher_start"], "PROVIDER_STALE")
            signal.pidfd_send_signal(fd, 0)
        finally: os.close(fd)
        return r

    def capture(self, nodes, timeout=6):
        expected = {n["id"] for n in nodes}
        if not expected: return {}
        requested = time.monotonic_ns()
        atomic(self.directory / "request.json", {"expires_ns": requested + int(timeout * 1e9)})
        def collect():
            try:
                rows = [self._valid(self.directory / f"{i}.json") for i in sorted(expected)]
                if any(r["observed_ns"] < requested for r in rows): return None
            except (OSError, Failure): return None
            require(len({r["publisher_pid"] for r in rows}) == 1, "PROVIDER_MULTIPLE_PROFILES_UNSUPPORTED")
            require(len({r["uuid"] for r in rows}) == len(rows), "EXACT_WINDOW_IDENTITY_COLLISION")
            live = {n["id"]: n for n in self.sway.windows()}
            require(expected.issubset(live), "APPLICATION_WINDOWS_INCOMPLETE")
            # Ne livrer qu'après retrait du préfixe, sans conserver les titres.
            if any((live[i].get("name") or "").startswith("[LABFY:") for i in expected): return None
            return {r["uuid"]: r["con_id"] for r in rows}
        try: return until(collect, timeout, "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE")
        finally: atomic(self.directory / "request.json", {"expires_ns": 0})

    def resolve(self, expected, nodes, timeout=6):
        result = self.capture(nodes, timeout)
        require(set(expected).issubset(result), "EXACT_WINDOW_IDENTITY_MISSING")
        # Les autres fenêtres peuvent correspondre à des slots explicitement
        # interchangeables ; la cardinalité applicative est vérifiée par l'executor.
        return result
