"""Application policy from explicit overrides and installed desktop entries.

Snapshots select a catalogue ID, never an executable, argument or terminal
command. Desktop discovery uses GIO's XDG precedence; launch uses that same
installed file, verified again before one GIO launch request.
"""
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
from .errors import require, Failure
from .ipc import X11_CLASS_PREFIX, surface_identity
from .schema import IDENT


@dataclass(frozen=True)
class Spec:
    application_id: str
    desktop_entry: str
    app_ids: tuple
    strategy: str
    argv: tuple
    provider: str | None = None
    managed_by: str | None = None
    desktop_signature: tuple | None = None


DEFAULT = (
    Spec("limusic", "limusic.desktop", ("limusic-app",), "managed-autostart", (), managed_by="sway-autostart"),
    Spec("firefox", "firefox.desktop", ("firefox", "org.mozilla.firefox"), "browser-self-restore", ("/usr/bin/firefox",), "firefox-session-window-uuid"),
    Spec("kitty", "kitty.desktop", ("kitty",), "terminal", ("/usr/bin/kitty",)),
    Spec("chatgpt", "chatgpt.desktop", (X11_CLASS_PREFIX + "Chatgpt",), "single-window", ("/usr/bin/chatgpt",)),
    Spec("proton-pass", "proton-pass.desktop", ("proton-pass",), "single-window", ("/usr/bin/proton-pass",)),
    Spec("whatsapp-web", "firefox.webapp-fcd72ebe-94c5-4209-b3f6-bbaa7784cded.desktop",
         ("firefox.webapp-fcd72ebe-94c5-4209-b3f6-bbaa7784cded",), "managed-autostart", (), managed_by="sway-autostart"),
    Spec("immich-web", "firefox.webapp-40f22022-70af-4784-81ee-100e6a56dc50.desktop",
         ("firefox.webapp-40f22022-70af-4784-81ee-100e6a56dc50",), "managed-autostart", (), managed_by="sway-autostart"),
)

# Shared interpreters/launchers provide no application identity.
WRAPPERS = frozenset(("env", "sh", "bash", "dash", "zsh", "fish", "flatpak",
                     "snap", "java", "javaw", "python", "python2", "python3",
                     "perl", "ruby", "node", "nodejs", "electron", "AppRun",
                     "gio", "gtk-launch", "xdg-open", "uwsm", "systemd-run"))


def _gio():
    try:
        import gi
        gi.require_version("Gio", "2.0")
        gi.require_version("GioUnix", "2.0")
        from gi.repository import Gio, GioUnix, GLib
        return Gio, GioUnix, GLib
    except (ImportError, ValueError):
        raise Failure("CATALOG_DISCOVERY_UNAVAILABLE") from None


def _desktop_signature(filename):
    """Pin an installed regular file, allowing Flatpak export symlinks."""
    path = Path(filename)
    require(path.is_absolute(), "APPLICATION_LAUNCH_FAILED")
    resolved = path.resolve(strict=True)
    # NONBLOCK + fstat before reading prevents a replaced FIFO/device from
    # blocking catalogue discovery; NOFOLLOW closes the final symlink race.
    descriptor = os.open(resolved, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid in (0, os.getuid())
                and not info.st_mode & 0o022 and info.st_size <= 262144,
                "APPLICATION_LAUNCH_FAILED")
        raw = stream.read(262145)
        final = os.fstat(stream.fileno())
    require(len(raw) <= 262144 and (info.st_size, info.st_mtime_ns) ==
            (final.st_size, final.st_mtime_ns), "APPLICATION_LAUNCH_FAILED")
    return (str(resolved), info.st_dev, info.st_ino, info.st_mtime_ns,
            info.st_size, hashlib.sha256(raw).hexdigest())


def _identity(value):
    return (isinstance(value, str) and 0 < len(value) <= 240
            and not value.startswith(X11_CLASS_PREFIX)
            and not any(ord(c) < 32 for c in value))


def installed_specs(apps=None, reserved=DEFAULT):
    """Discover exact identities, never infer a match from title or PID args.

    GIO resolves local/system/Flatpak precedence and Hidden overrides. Menu
    visibility (NoDisplay/OnlyShowIn) does not determine window support. Explicit
    policy remains authoritative. Declared identities outrank executable-name
    fallbacks; equal-rank collisions are removed from every candidate.
    """
    Gio, GioUnix, GLib = _gio()
    apps = tuple(Gio.AppInfo.get_all() if apps is None else apps)
    require(len(apps) <= 4096, "CATALOG_LIMIT")
    reserved_entries = {s.desktop_entry for s in reserved}
    reserved_names = {s.desktop_entry[:-8] for s in reserved}
    reserved_names.update(identity.removeprefix(X11_CLASS_PREFIX)
                          for s in reserved for identity in s.app_ids)
    reserved_ids = reserved_names | {X11_CLASS_PREFIX + value for value in reserved_names}
    candidates, aliases, excluded = {}, {}, {}
    for app in sorted(apps, key=lambda a: a.get_id() or ""):
        if not isinstance(app, GioUnix.DesktopAppInfo): continue
        identifier = app.get_id()
        if identifier in reserved_entries:
            continue
        if not isinstance(identifier, str) or not IDENT.fullmatch(identifier) or not identifier.endswith(".desktop"):
            continue
        reason = None
        if app.get_is_hidden(): reason = "hidden"
        elif app.get_string("Type") != "Application": reason = "not-application"
        elif app.get_boolean("Terminal"): reason = "terminal-content"
        elif identifier.startswith("firefox.webapp-"): reason = "provider-required"
        filename = app.get_filename()
        if not reason and not filename: reason = "no-desktop-file"
        executable = None
        if not reason:
            try:
                commandline = app.get_commandline()
                if commandline:
                    parsed, argv = GLib.shell_parse_argv(commandline)
                    if parsed and argv:
                        executable = argv[0]
                if not app.get_boolean("DBusActivatable") and not (executable and shutil.which(executable)):
                    reason = "executable-unavailable"
                signature = _desktop_signature(filename)
            except (OSError, ValueError, GLib.Error, Failure):
                reason = "invalid-desktop-file"
        if reason:
            excluded[identifier] = reason
            continue
        # desktop_entry itself is a stable, schema-valid ID in its own namespace.
        spec = Spec(identifier, identifier, (), "application-self-restore",
                    ("/usr/bin/gio", "launch", filename), desktop_signature=signature)
        candidates[identifier] = spec
        values = {}
        def add(value, rank):
            if _identity(value):
                values[value] = max(rank, values.get(value, 0))
        stem = identifier[:-8]
        add(stem, 3)
        # Legacy X11 fallback remains exact and case-sensitive.
        if _identity(stem): values[X11_CLASS_PREFIX + stem] = 1
        wm_class = app.get_startup_wm_class()
        add(wm_class, 2)
        if _identity(wm_class): values[X11_CLASS_PREFIX + wm_class] = 2
        basename = Path(executable).name if executable else ""
        if basename and basename not in WRAPPERS:
            add(basename, 1)
            if _identity(basename): values[X11_CLASS_PREFIX + basename] = max(1, values.get(X11_CLASS_PREFIX + basename, 0))
        for identity, rank in values.items():
            if identity not in reserved_ids:
                aliases.setdefault(identity, []).append((rank, identifier))
    accepted = {identifier: [] for identifier in candidates}
    for identity, owners in aliases.items():
        rank = max(r for r, _ in owners)
        best = {identifier for r, identifier in owners if r == rank}
        if len(best) == 1:
            accepted[next(iter(best))].append(identity)
    result = []
    for identifier, spec in candidates.items():
        if accepted[identifier]:
            result.append(replace(spec, app_ids=tuple(sorted(accepted[identifier]))))
        else:
            excluded[identifier] = "ambiguous-identity"
    return tuple(result), excluded


class Catalog:
    def __init__(self, specs=None, *, desktop_apps=None):
        # Explicit test/plugin catalogues are hermetic: no installed discovery.
        self.excluded = {}
        if specs is None:
            discovered, self.excluded = installed_specs(desktop_apps)
            specs = DEFAULT + discovered
        else:
            require(desktop_apps is None, "CATALOG_ARGUMENTS")
            specs = tuple(specs)
        self.specs = {s.application_id: s for s in specs}
        require(len(self.specs) == len(specs), "CATALOG_DUPLICATE")
        ids = [v for s in specs for v in s.app_ids]
        require(len(ids) == len(set(ids)), "CATALOG_AMBIGUOUS")

    def classify(self, node):
        identity = surface_identity(node)
        found = [s for s in self.specs.values() if identity in s.app_ids]
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
    if strategy in ("browser-self-restore", "application-self-restore"):
        # Never request N launches for a generic single-instance application.
        # Its full saved window set must appear before any layout mutation.
        return 1 if observed == 0 else 0
    if strategy in ("terminal", "multi-instance"): return n - observed
    raise Failure("APPLICATION_UNSUPPORTED")


def launch(spec, count, env=None):
    require(type(count) is int and 0 <= count <= 256, "LAUNCH_BOUNDS")
    if spec.strategy == "application-self-restore":
        require(count <= 1 and spec.desktop_signature is not None
                and spec.argv[:2] == ("/usr/bin/gio", "launch") and len(spec.argv) == 3,
                "APPLICATION_LAUNCH_FAILED")
        if count:
            require(_desktop_signature(spec.argv[2]) == spec.desktop_signature,
                    "APPLICATION_LAUNCH_FAILED")
    children = []
    for _ in range(count):
        # Applications survive restoration errors; only owned helpers are killed.
        children.append(subprocess.Popen(list(spec.argv), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True))
    return children
