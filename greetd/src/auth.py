"""Machine PAM indépendante de GTK pour préserver les invites multiples."""
from greetd_ipc import Client, ProtocolError, session_command


class AuthFlow:
    def __init__(self, socket_path=None):
        self.socket_path = socket_path
        self.client = None
        self.username = None
        self.pending = None
        self.authenticated = False
        self.selection = None

    def begin(self, username, selection="stable"):
        self.reset()
        session_command(selection)
        if type(username) is not str or not username or len(username) > 256 or any(ord(c) < 32 for c in username):
            raise ValueError("Nom utilisateur invalide")
        # CONTRACT: compte et choix sont figés pour toute cette conversation PAM.
        # Le thread GTK ne les modifie pas ; un nouveau begin annule l'ancien état.
        self.username = username
        self.selection = selection
        try:
            self.client = Client(self.socket_path)
            return self._accept(self.client.create(username))
        except (OSError, ProtocolError):
            self.reset()
            raise

    def answer(self, value=None):
        if self.pending is None or self.client is None:
            raise ProtocolError("Aucune invite PAM active")
        kind = self.pending["auth_message_type"]
        if kind in ("secret", "visible") and value is None:
            raise ProtocolError("Réponse PAM requise")
        if kind in ("info", "error"):
            value = None
        self.pending = None
        try:
            return self._accept(self.client.answer(value))
        except (OSError, ProtocolError):
            self.reset()
            raise

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
        # INVARIANT: un seul start par authentification, succès ou refus ; aucun repli.
        self.authenticated = False
        try:
            reply = self.client.start(self.selection)
        except (OSError, ProtocolError):
            self.reset()
            raise
        if reply["type"] == "success":
            self.client.close()
            self.client = None
            self.username = None
            self.selection = None
        else:
            self.reset()
        return reply

    def reset(self):
        if self.client is not None:
            try:
                self.client.cancel()
            except (OSError, ProtocolError):
                pass
            self.client.close()
        self.client = None
        self.username = None
        self.selection = None
        self.pending = None
        self.authenticated = False
