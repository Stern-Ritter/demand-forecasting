class NotFoundException(Exception):
    """Raised when a forecast job referenced by a queue message does not exist.

    The worker is a headless consumer and must not depend on the web layer
    (FastAPI), so it uses this lightweight exception instead of ``app.exceptions``.
    """

    def __init__(self, detail: str = "Resource not found"):
        self.detail = detail
        super().__init__(detail)
