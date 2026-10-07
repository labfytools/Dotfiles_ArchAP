"""Énumération NSS des comptes humains sans fixer un nom d'utilisateur."""
import pwd


def uid_limits(path="/etc/login.defs"):
    limits = {"UID_MIN": 1000, "UID_MAX": 60000}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            parts = line.split("#", 1)[0].split()
            if len(parts) == 2 and parts[0] in limits:
                limits[parts[0]] = int(parts[1])
    return limits["UID_MIN"], limits["UID_MAX"]


def users(entries=None, limits=None):
    entries = pwd.getpwall() if entries is None else entries
    low, high = uid_limits() if limits is None else limits
    return sorted((entry.pw_name for entry in entries if low <= entry.pw_uid <= high
                   and entry.pw_shell.rsplit("/", 1)[-1] not in ("nologin", "false")
                   and entry.pw_name), key=str.casefold)
