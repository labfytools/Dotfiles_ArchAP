"""Host production candidat : map-window et attestation bootstrap ; Sway GET_TREE/GET_VERSION en lecture seule.

WHY : corrélation par jeton sans lire le suffixe sémantique ni l'exporter.
CONTRACT : message natif <=4096, clés exactes, aucun shell/argv reçu.
INVARIANT : publication privée runtime seulement, sans URL/titre/environnement.
"""
import json
import os
import re
import select
from pathlib import Path
import struct
import sys
import time
from .errors import require, Failure
from .schema import UUID, PROVIDER
from .storage import loads, atomic, private_dir, state_path, read
from .ipc import Sway
from .firefox_identity import FirefoxProvider, process_start, validate_record

EXTENSION_ID = "session-v2@labfy.org"
APP_IDS = {"firefox", "org.mozilla.firefox"}


def validate(message):
    require(type(message) is dict, "MESSAGE_SCHEMA")
    if message == {"op": "bootstrap-eligibility"}:
        return message
    require(set(message) == {"op", "uuid", "runtime_token"}, "MESSAGE_SCHEMA")
    require(message["op"] == "map-window", "OP_NOT_ALLOWED")
    require(type(message["uuid"]) is str and UUID.fullmatch(message["uuid"]), "INVALID_UUID")
    require(type(message["runtime_token"]) is str and re.fullmatch(r"[0-9a-f]{32}", message["runtime_token"]), "INVALID_TOKEN")
    return message


def bootstrap_eligibility(sway=None):
    """WHY : install inclut la réinstallation ; seul le store fait autorité.

    CONTRACT : observation sans création, contenu ni chemin dans la réponse.
    Toute présence de last.json ou d'une entrée sessions, ou erreur, refuse.
    Aucun contenu n'est ouvert. Parcours par
    FD NOFOLLOW : aucun lien parent/final suivi, aucun FIFO ouvert. Les FD
    restent bornés à deux, même pour un chemin profond.
    INVARIANT : attestation instantanée seulement, aucun verrou/CAS avec Firefox.
    """
    directory = None
    try:
        # GET_VERSION revalide inode/session du socket et UID du pair sans
        # observer de fenêtres. Toute rupture de cette autorité refuse aussi.
        if sway is not None: sway.request(7)
        root = state_path()
        require(len(os.fsencode(root)) <= 4096, "PATH_BOUNDS")
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for index, part in enumerate(root.parts[1:]):
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=directory)
            except FileNotFoundError:
                return {"result": "OK", "baseline_enrollment_allowed": True}
            os.close(directory)
            directory = child
            info = os.fstat(directory)
            # Une absence sous un parent illisible n'est jamais attestée,
            # même si l'UID privilégié du runner pourrait contourner ses bits.
            require(info.st_mode & 0o444 and info.st_mode & 0o111, "DIRECTORY_UNREADABLE")
            # Les deux niveaux du namespace doivent être privés et lisibles.
            # Vérifier les bits aussi sous un test lancé comme root.
            if index >= len(root.parts[1:]) - 2:
                require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0
                        and info.st_mode & 0o500 == 0o500, "DIRECTORY_PERMISSIONS")
        # Une branche absente n'atteste jamais l'absence de sa sœur.
        # Garder le FD racine : ni résolution absolue ni création du store.
        for branch in ("automatic", "sessions"):
            try:
                child = os.open(branch, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=directory)
            except FileNotFoundError:
                continue
            try:
                info = os.fstat(child)
                require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0
                        and info.st_mode & 0o500 == 0o500, "DIRECTORY_PERMISSIONS")
                if branch == "sessions":
                    # Budget conservateur avant listdir ; un grand répertoire
                    # refuse sans énumération. Aucun nom n'est exporté/ouvert.
                    require(info.st_size <= 65536, "DIRECTORY_BOUNDS")
                    if os.listdir(child):
                        return {"result": "OK", "baseline_enrollment_allowed": False}
                else:
                    try: os.stat("last.json", dir_fd=child, follow_symlinks=False)
                    except FileNotFoundError: continue
                    return {"result": "OK", "baseline_enrollment_allowed": False}
            finally:
                os.close(child)
        return {"result": "OK", "baseline_enrollment_allowed": True}
    except (OSError, ValueError, Failure):
        pass
    finally:
        if directory is not None: os.close(directory)
    return {"result": "OK", "baseline_enrollment_allowed": False}


def take(stream, n, timeout=5):
    end, result = time.monotonic() + timeout, bytearray()
    while len(result) < n:
        require(time.monotonic() < end and select.select([stream], [], [], max(0, end - time.monotonic()))[0], "MESSAGE_TIMEOUT")
        data = stream.read(n - len(result))
        if not data: raise EOFError()
        result.extend(data)
    return bytes(result)


def receive(stream):
    size, = struct.unpack("=I", take(stream, 4))
    require(0 < size <= 4096, "MESSAGE_BOUNDS")
    return validate(loads(take(stream, size), 4096))


def send(stream, value):
    raw = json.dumps(value, separators=(",", ":")).encode()
    require(len(raw) <= 4096, "MESSAGE_BOUNDS")
    stream.write(struct.pack("=I", len(raw)) + raw)
    stream.flush()


def correlate(sway, message):
    validate(message)
    require(message["op"] == "map-window", "OP_NOT_ALLOWED")
    prefix = "[LABFY:" + message["runtime_token"] + "] "
    end = time.monotonic() + 2
    while True:
        found = [n["id"] for n in sway.windows() if n.get("app_id") in APP_IDS and (n.get("name") or "").startswith(prefix)]
        require(len(found) <= 1, "EXACT_WINDOW_IDENTITY_COLLISION")
        if found: return found[0]
        require(time.monotonic() < end, "CORRELATION_TIMEOUT")
        time.sleep(.02)


def main():
    # Firefox transmet manifest + ID. Le manifest allowlist est l'autorité ;
    # l'ID est aussi contrôlé ici, sans accepter de paramètres de configuration.
    require(len(sys.argv) == 3 and sys.argv[2] == EXTENSION_ID, "EXTENSION_NOT_ALLOWED")
    sway = Sway(os.environ.get("SWAYSOCK", ""))
    # Ne pas initialiser le store pour une simple observation bootstrap.
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", ""))
    require(runtime.is_absolute(), "XDG_PATH_INVALID")
    private_dir(runtime)
    runtime = private_dir(runtime / "labfy-sway")
    provider = FirefoxProvider(sway, runtime)
    last_request = 0
    while True:
        try:
            # Le host ne demande une corrélation que pendant une requête locale
            # bornée du moteur ; aucun clignotement de préfixe en idle.
            if not select.select([sys.stdin.buffer.raw], [], [], .1)[0]:
                try:
                    request = read(provider.directory / "request.json")
                    now = time.monotonic_ns()
                    if type(request) is dict and set(request) == {"expires_ns"} and type(request["expires_ns"]) is int and now < request["expires_ns"] <= now + 10_000_000_000 and now - last_request > 500_000_000:
                        send(sys.stdout.buffer, {"event": "capture"})
                        last_request = now
                except FileNotFoundError: pass
                continue
            message = receive(sys.stdin.buffer.raw)
            if message["op"] == "bootstrap-eligibility":
                send(sys.stdout.buffer, bootstrap_eligibility(sway))
                continue
            identity = correlate(sway, message)
            record = {"schema": PROVIDER, "version": 1, "session": sway.session, "uuid": message["uuid"],
                      "con_id": identity, "observed_ns": time.monotonic_ns(), "publisher_pid": os.getpid(),
                      "publisher_start": process_start(os.getpid())}
            atomic(provider.directory / f"{identity}.json", record, validate_record)
            # Collecte des seules observations périmées de ce namespace possédé.
            for p in list(provider.directory.glob("*.json"))[:512]:
                if not p.stem.isdigit() or p.name == f"{identity}.json": continue
                if time.time() - p.stat().st_mtime > 10: p.unlink()
            send(sys.stdout.buffer, {"result": "OK", "uuid": message["uuid"], "con_id": identity})
        except EOFError: return
        except Failure as exc:
            send(sys.stdout.buffer, {"result": exc.code})
            # Après un framing invalide il n'existe aucun point de resynchronisation.
            if exc.code.startswith(("MESSAGE_", "JSON_")): return
        except (OSError, ValueError, RecursionError):
            send(sys.stdout.buffer, {"result": "FIREFOX_IDENTITY_PROVIDER_UNAVAILABLE"})
            return


if __name__ == "__main__":
    try: main()
    except (Failure, OSError): sys.exit(1)
