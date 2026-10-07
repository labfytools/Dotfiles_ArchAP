"""Politique au niveau Application ; argv viennent du catalogue de confiance.

Le snapshot sélectionne seulement une entrée exacte du catalogue. Il ne peut
introduire aucun exécutable, argument, commande shell ni commande de terminal.
"""
from dataclasses import dataclass
import subprocess
from .errors import require, Failure


@dataclass(frozen=True)
class Spec:
    application_id: str
    desktop_entry: str
    app_ids: tuple
    strategy: str
    argv: tuple
    provider: str | None = None
    managed_by: str | None = None


DEFAULT = (
    Spec("limusic", "limusic.desktop", ("limusic-app",), "managed-autostart", (), managed_by="sway-autostart"),
    Spec("firefox", "firefox.desktop", ("firefox", "org.mozilla.firefox"), "browser-self-restore", ("/usr/bin/firefox",), "firefox-session-window-uuid"),
    Spec("kitty", "kitty.desktop", ("kitty",), "terminal", ("/usr/bin/kitty",)),
)


class Catalog:
    def __init__(self, specs=DEFAULT):
        self.specs = {s.application_id: s for s in specs}
        require(len(self.specs) == len(specs), "CATALOG_DUPLICATE")
        ids = [v for s in specs for v in s.app_ids]
        require(len(ids) == len(set(ids)), "CATALOG_AMBIGUOUS")

    def classify(self, node):
        found = [s for s in self.specs.values() if node.get("app_id") in s.app_ids]
        require(len(found) == 1, "APPLICATION_UNSUPPORTED")
        return found[0]

    def validate(self, app):
        require(app["application_id"] in self.specs, "APPLICATION_UNSUPPORTED")
        s = self.specs[app["application_id"]]
        require(app["desktop_entry"] == s.desktop_entry and app["strategy"] == s.strategy and app["identity_provider"] == s.provider,
                "APPLICATION_POLICY_MISMATCH")
        require(s.strategy != "unknown", "APPLICATION_UNSUPPORTED")
        owner = (s.managed_by or "autostart") if s.strategy == "managed-autostart" else None
        require(app["managed_by"] == owner, "APPLICATION_POLICY_MISMATCH")
        return s


def launch_count(app, observed):
    n = app["expected_windows"]
    require(0 <= observed <= n, "UNEXPECTED_EXTRA_WINDOW")
    strategy = app["strategy"]
    if strategy == "managed-autostart": return 0
    if strategy == "single-window":
        require(n == 1, "APPLICATION_POLICY_MISMATCH")
        return 1 - observed
    if strategy == "browser-self-restore":
        # Une instance déjà présente n'autorise jamais une deuxième ouverture.
        return 1 if observed == 0 else 0
    if strategy in ("terminal", "multi-instance"): return n - observed
    raise Failure("APPLICATION_UNSUPPORTED")


def launch(spec, count, env=None):
    require(type(count) is int and 0 <= count <= 256, "LAUNCH_BOUNDS")
    children = []
    for _ in range(count):
        # Les applications ne sont pas des ressources jetables : jamais tuées
        # automatiquement lors d'un échec de restauration.
        children.append(subprocess.Popen(list(spec.argv), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True))
    return children
