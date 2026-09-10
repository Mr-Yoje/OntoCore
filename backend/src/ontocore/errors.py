class ProfileViolation(Exception):
    pass


class OntologyWriteError(Exception):
    pass


class ConflictError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class IngressError(Exception):
    pass


class GraphUnavailable(Exception):
    pass


class StructuredOutputError(Exception):
    pass
