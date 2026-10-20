"""Exception type used by services to report expected, user-facing problems."""


class ServiceError(Exception):
    """A rule was broken (duplicate, deadline passed, not allowed, ...).

    ``message`` is safe to show to the user. ``code`` is a short machine
    readable reason used by tests and the scanner API.
    """

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code
