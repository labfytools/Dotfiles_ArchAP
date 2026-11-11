#!/usr/bin/python3
"""Publie un instantané Arch/AUR borné pour la barre QuickShell."""

import datetime
import fcntl
import functools
import re
import socket
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import time
import json
import os
import pathlib
import subprocess
import sys
import tempfile


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def publish(destination, state):
    # CONTRACT: readers only see complete UTF-8 snapshots, never a partial write.
    fd, temporary = tempfile.mkstemp(prefix="labfy-updates-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_cache(path):
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


@functools.lru_cache(maxsize=1)
def kernel_names():
    names = set()
    for path in pathlib.Path("/usr/lib/modules").glob("*/pkgbase"):
        try:
            names.add(path.read_text().strip())
        except OSError:
            pass
    return names


def sensitive(name):
    # WHY: component families are informational, never a prediction of breakage.
    if re.fullmatch(r"linux(?:-zen|-lts|-hardened|-rt|-rt-lts)?(?:-headers)?", name):
        return "Noyau"
    if name.startswith("systemd") or name == "pacman":
        return "Système"
    if any(part in name for part in ("mesa", "nvidia", "vulkan", "xf86-video", "amdgpu", "amdvlk", "intel-media-driver", "libva-intel-driver", "linux-firmware-intel")):
        return "Graphique"
    if name.startswith(("sway", "quickshell")):
        return "Session"
    # Custom installed kernels also expose a pkgbase under /usr/lib/modules.
    if name in kernel_names():
        return "Noyau"
    return ""


def packages(command, origin):
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False,
                            env={**os.environ, "LC_ALL": "C", "NO_COLOR": "1"})
    empty_code = 2 if command[0] == "checkupdates" else 1
    if result.returncode == empty_code and not (result.stdout.strip() or result.stderr.strip()):
        return []
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f"Code {result.returncode}").strip()[:500])
    rows = []
    # yay -Qua may append relative age [12h36m] or [2d3h]; it is not
    # part of the available package version. Permit bounded AUR metadata only.
    age = r"(?: \[(?:[0-9]{1,4}[a-zA-Z]{1,3}){1,8}\])?" if origin == "AUR" else ""
    for line in result.stdout.splitlines():
        match = re.fullmatch(r"([a-zA-Z0-9@._+:-]+) (\S+) -> (\S+)" + age, line.strip())
        if not match:
            raise RuntimeError("Sortie du collecteur inattendue : " + line[:160])
        name, installed, available = match.groups()
        rows.append(dict(name=name, installed=installed, available=available,
                         origin=origin, sensitive=sensitive(name)))
    return rows


def offline():
    # A failed collector is not necessarily a network failure. Probe only on error.
    try:
        with socket.create_connection(("archlinux.org", 443), timeout=3):
            return False
    except OSError:
        return True


def check(runtime):
    destination = runtime / "labfy-quickshell-updates.json"
    state = read_cache(destination)
    # CONTRACT: corrupt cached data must not prevent a fresh check from recovering.
    valid = all(type(state.get(key)) is int and state[key] >= 0
                for key in ("repoUpdates", "aurUpdates", "totalUpdates"))
    rows = state.get("packages", [])
    valid = valid and state["totalUpdates"] == state["repoUpdates"] + state["aurUpdates"]
    valid = valid and isinstance(rows, list) and all(isinstance(row, dict)
        and all(isinstance(row.get(key), str) for key in ("name", "installed", "available"))
        and row.get("origin") in ("Arch", "AUR") for row in rows)
    if not valid:
        state = dict(repoUpdates=0, aurUpdates=0, totalUpdates=0,
                     packages=[], lastCheck="", error="")
    state.update(checking=True, checkStarted=now(), error="", offline=False)
    publish(destination, state)
    errors = []
    try:
        for origin, command, key in (("Arch", ["checkupdates", "--nocolor"], "repoUpdates"),
                                     ("AUR", ["yay", "-Qua", "--color", "never"], "aurUpdates")):
            try:
                rows = packages(command, origin)
                state["packages"] = [p for p in state.get("packages", []) if p["origin"] != origin] + rows
                state[key] = len(rows)
            except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
                errors.append(origin + " : " + str(exc)[:500])
        state["totalUpdates"] = state["repoUpdates"] + state["aurUpdates"]
        state["lastCheck"] = now()
        if not errors:
            state["lastSuccess"] = state["lastCheck"]
        state["error"] = " ; ".join(errors)
        state["offline"] = offline() if errors else False
    finally:
        state["checking"] = False
        publish(destination, state)
    return bool(errors)


def output(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=12, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or f"{command[0]} : code {result.returncode}").strip()[:300])
    return result.stdout


def maintenance():
    result = dict(time=now(), history=[], files=[], failed=[], reboot="", errors=[])
    try:
        # Read a bounded tail even when pacman.log has years of transactions.
        with open("/var/log/pacman.log", "rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 262144))
            lines = stream.read(262144).decode("utf-8", "replace").splitlines()
        result["history"] = [line for line in lines if "[ALPM]" in line and any(
            word in line for word in ("upgraded ", "installed ", "removed ", "transaction "))][-35:][::-1]
    except OSError as exc:
        result["errors"].append(str(exc))
    # CONTRACT: /etc scan is read-only, does not follow symlinks, and reports limits.
    errors = result["errors"]
    visited = 0
    deadline = time.monotonic() + 4
    def walk_error(exc):
        if len(errors) < 12:
            errors.append(str(exc))
    for root, dirs, files in os.walk("/etc", followlinks=False, onerror=walk_error):
        visited += len(dirs) + len(files)
        if visited > 50000 or time.monotonic() > deadline:
            errors.append("Recherche /etc incomplète : limite de lecture atteinte")
            break
        for name in files:
            if name.endswith((".pacnew", ".pacsave")):
                result["files"].append(str(pathlib.Path(root) / name))
    result["files"].sort()
    for scope in ([], ["--user"]):
        try:
            lines = output(["systemctl", *scope, "--failed", "--no-legend", "--plain", "--no-pager"]).splitlines()
            result["failed"] += [("Utilisateur : " if scope else "Système : ") + line for line in lines[:30]]
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            errors.append(str(exc))
    if pathlib.Path("/run/reboot-required").exists():
        result["reboot"] = "Demande de redémarrage détectée : /run/reboot-required."
    elif not pathlib.Path("/usr/lib/modules", os.uname().release).exists():
        result["reboot"] = "Recommandation : modules du noyau actif absents ; un redémarrage peut être nécessaire."
    else:
        result["reboot"] = "Aucun signal certain détecté. Un redémarrage peut rester conseillé après noyau, pilotes ou systemd."
    return result


def parse_news(data):
    root = ET.fromstring(data)
    items = []
    for item in root.findall("./channel/item")[:12]:
        title = (item.findtext("title") or "")[:500]
        link = item.findtext("link") or ""
        url = urllib.parse.urlparse(link)
        if url.scheme != "https" or url.netloc != "archlinux.org":
            continue
        # Only an explicit editorial statement in the official title is labeled.
        explicit = bool(re.search(r"manual intervention (?:is )?required|requires manual intervention", title, re.I))
        items.append(dict(title=title, date=(item.findtext("pubDate") or "")[:100],
                          link=link, manual=explicit))
    return items


def news():
    cache = pathlib.Path(os.environ.get("XDG_CACHE_HOME", str(pathlib.Path.home() / ".cache"))) / "labfy-update-news.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    old = read_cache(cache)
    if time.time() - old.get("fetched", 0) < 21600:
        return old
    # Negative caching also prevents repeated network attempts while offline.
    result = dict(old, error="", attempted=time.time())
    if time.time() - old.get("attempted", 0) < 600:
        return old
    try:
        request = urllib.request.Request("https://archlinux.org/feeds/news/", headers={"User-Agent": "Labfy-Update-Center/1"})
        with urllib.request.urlopen(request, timeout=12) as response:
            data = response.read(1048577)
        if len(data) > 1048576:
            raise ValueError("Flux trop volumineux")
        result.update(items=parse_news(data), fetched=time.time(), time=now())
    except (OSError, ValueError, ET.ParseError) as exc:
        result["error"] = "Flux indisponible, cache conservé : " + str(exc)[:250]
    publish(cache, result)
    return result


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode in ("maintenance", "news"):
        print(json.dumps(maintenance() if mode == "maintenance" else news(), ensure_ascii=False))
        return 0
    if mode != "check":
        return 2
    runtime = pathlib.Path(os.environ["XDG_RUNTIME_DIR"])
    # Shared with the interactive installer: timer, direct invocation and all outputs
    # cannot start overlapping package operations. Lifetime is the open descriptor.
    with open(runtime / "labfy-updates.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return int(check(runtime))


if __name__ == "__main__":
    raise SystemExit(main())
