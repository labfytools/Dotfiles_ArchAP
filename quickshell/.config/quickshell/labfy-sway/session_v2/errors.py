class Failure(Exception):
    """Codes stables uniquement ; aucune exception externe ni contenu utilisateur."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition: raise Failure(code)
