"""Machine PAM indépendante de GTK pour préserver les invites multiples."""
from greetd_ipc import Client, ProtocolError


class AuthFlow:
    def __init__(self, socket_path=None):
        self.socket_path = socket_path
        self.client = None
        self.username = None
        self.pending = None
        self.authenticated = False

    def begin(self, username):
        if not username or len(username) > 256 or any(ord(c) < 32 for c in username):
            raise ValueError("Nom utilisateur invalide")
        self.reset()
        self.username = username
        self.client = Client(self.socket_path)
        return self._accept(self.client.create(username))

    def answer(self, value=None):
        if self.pending is None or self.client is None:
            raise ProtocolError("Aucune invite PAM active")
        kind = self.pending["auth_message_type"]
        if kind in ("secret", "visible") and value is None:
            raise ProtocolError("Réponse PAM requise")
        if kind in ("info", "error"):
            value = None
        self.pending = None
        return self._accept(self.client.answer(value))

    def _accept(self, reply):
        self.pending = None
        if reply["type"] == "auth_message":
            self.pending = reply
        elif reply["type"] == "success":
            self.authenticated = True
        elif reply["type"] == "error":
            self.reset()
        return reply

    def start(self):
        if not self.authenticated or self.client is None:
            raise ProtocolError("Session non authentifiée")
        reply = self.client.start()
        if reply["type"] == "success":
            self.client.close()
            self.client = None
        return reply

    def reset(self):
        if self.client is not None:
            try:
                self.client.cancel()
            except (OSError, ProtocolError):
                pass
            self.client.close()
        self.client = None
        self.pending = None
        self.authenticated = False
