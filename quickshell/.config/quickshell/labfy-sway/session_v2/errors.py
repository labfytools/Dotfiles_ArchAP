class Failure(Exception):
    """Codes stables uniquement ; aucune exception externe ni contenu utilisateur."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Deferred(Failure):
    """Refus avant transaction : retry explicite possible, jamais automatique.

    CONTRACT : conserve le code de cause ; aucune publication Recovery/Attempt
    ni commande de placement ne doit précéder ce résultat.
    """


def require(condition, code):
    if not condition: raise Failure(code)
