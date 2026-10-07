class AppError(Exception):
    """`message` is English with {placeholders} filled from `params` after
    it is translated: `t(exc.message, **exc.params)`."""

    def __init__(self, code: str, message: str, status_code: int = 400, **params: object) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.params = params
