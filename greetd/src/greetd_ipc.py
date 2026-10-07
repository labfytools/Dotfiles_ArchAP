"""Client borné pour le protocole greetd-ipc(7)."""
import json
import os
import socket
import struct

MAX_FRAME = 65536
SESSION_COMMAND = ["/usr/bin/uwsm", "start", "default"]


class ProtocolError(Exception):
    pass


class Client:
    """Une connexion par conversation PAM ; aucun contenu secret n'est journalisé."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("GREETD_SOCK")
        if not self.path:
            raise ProtocolError("Socket greetd indisponible")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        try:
            self.sock.connect(self.path)
        except OSError:
            self.sock.close()
            raise

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def request(self, message):
        # CONTRACT: longueur native uint32 suivie de JSON UTF-8, sans données sensibles en logs.
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_FRAME:
            raise ProtocolError("Message trop long")
        self.sock.sendall(struct.pack("=I", len(raw)) + raw)
        size = struct.unpack("=I", self._read(4))[0]
        if not 0 < size <= MAX_FRAME:
            raise ProtocolError("Réponse de taille invalide")
        try:
            reply = json.loads(self._read(size).decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ProtocolError("Réponse greetd invalide") from exc
        if not isinstance(reply, dict) or reply.get("type") not in ("success", "error", "auth_message"):
            raise ProtocolError("Type de réponse greetd invalide")
        if reply["type"] == "auth_message" and (reply.get("auth_message_type") not in ("secret", "visible", "info", "error") or not isinstance(reply.get("auth_message"), str)):
            raise ProtocolError("Message PAM invalide")
        if reply["type"] == "error" and reply.get("error_type") not in ("auth_error", "error"):
            raise ProtocolError("Erreur greetd invalide")
        return reply

    def _read(self, count):
        parts = []
        while count:
            part = self.sock.recv(count)
            if not part:
                raise ProtocolError("Connexion greetd interrompue")
            parts.append(part)
            count -= len(part)
        return b"".join(parts)

    def create(self, username):
        return self.request({"type": "create_session", "username": username})

    def answer(self, response=None):
        message = {"type": "post_auth_message_response"}
        if response is not None:
            message["response"] = response
        return self.request(message)

    def cancel(self):
        return self.request({"type": "cancel_session"})

    def start(self):
        # INVARIANT: la commande authentifiée est fixe et exécutée par greetd, jamais ici.
        return self.request({"type": "start_session", "cmd": SESSION_COMMAND, "env": []})
