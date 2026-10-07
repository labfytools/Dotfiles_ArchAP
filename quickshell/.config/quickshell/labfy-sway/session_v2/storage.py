"""Stockage privé : validation, NOFOLLOW, publication durable et lock partagé.

CONTRACT : le namespace est possédé par l'UID courant et non accessible aux
autres utilisateurs. Les verrous restent valides via FD hérité par le guard.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import uuid
from .errors import Failure, require

MAX_JSON = 1024 * 1024


def pairs(items):
    result = {}
    for k, v in items:
        require(k not in result, "JSON_DUPLICATE_KEY")
        result[k] = v
    return result


def loads(raw, limit=MAX_JSON):
    require(len(raw) <= limit, "JSON_TOO_LARGE")
    try: return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Failure("JSON_NUMBER")))
    except (ValueError, RecursionError): raise Failure("JSON_INVALID") from None


def private_dir(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "PATH_INVALID")
    # Refuser les liens dans toute la chaîne ; ne chmod jamais un parent existant.
    for part in [*reversed(path.parents), path]:
        if not part.exists() and not part.is_symlink():
            try: part.mkdir(mode=0o700)
            except FileExistsError: pass
        require(not part.is_symlink() and part.is_dir(), "PATH_SYMLINK")
    st = path.stat()
    require(st.st_uid == os.getuid() and stat.S_ISDIR(st.st_mode) and st.st_mode & 0o077 == 0, "DIRECTORY_PERMISSIONS")
    return path


def read(path, validator=lambda x: x):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_mode & 0o077 == 0, "FILE_PERMISSIONS")
        require(st.st_size <= MAX_JSON, "JSON_TOO_LARGE")
        with os.fdopen(fd, "rb", closefd=False) as stream: data = stream.read(MAX_JSON + 1)
        return validator(loads(data))
    finally: os.close(fd)


def atomic(path, data, validator=lambda x: x):
    path = Path(path)
    directory = private_dir(path.parent)
    validator(data)
    raw = (json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n").encode()
    require(len(raw) <= MAX_JSON, "JSON_TOO_LARGE")
    temporary = directory / (".tmp-" + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(read(temporary, validator) == data, "PUBLICATION_REREAD")
        require(not path.is_symlink(), "PATH_SYMLINK")
        os.replace(temporary, path)
        sync_dir(directory)
    finally:
        if temporary.exists(): temporary.unlink()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


@contextmanager
def lock(directory, name="transaction.lock"):
    directory = private_dir(directory)
    fd = os.open(directory / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_mode & 0o077 == 0, "LOCK_PERMISSIONS")
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise Failure("TRANSACTION_BUSY") from None
        yield fd
    finally: os.close(fd)


def paths():
    home = Path.home()
    state = Path(os.environ.get("XDG_STATE_HOME", str(home / ".local/state")))
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", ""))
    require(state.is_absolute() and runtime.is_absolute(), "XDG_PATH_INVALID")
    private_dir(runtime)
    return private_dir(state / "labfy-sway/session-v2"), private_dir(runtime / "labfy-sway")
