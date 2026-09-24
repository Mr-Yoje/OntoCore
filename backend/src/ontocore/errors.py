from ontocore.error_catalog import FAULTS


class AppError(Exception):
    code = "OC-9001"
    kind = "system"
    http_status = 500

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        kind: str | None = None,
        http_status: int | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        entry = FAULTS.get(self.code)
        if entry is not None:
            self.message = entry["detail"]
            self.kind = entry["kind"]
            self.http_status = entry["http_status"]
        else:
            self.message = message
            if kind is not None:
                self.kind = kind
            if http_status is not None:
                self.http_status = http_status
        super().__init__(self.message)


class BusinessError(AppError):
    code = "OC-1000"
    kind = "business"
    http_status = 400


class SystemError(AppError):
    code = "OC-9001"
    kind = "system"
    http_status = 500


class ProfileViolation(BusinessError):
    code = "OC-2001"


class OntologyWriteError(BusinessError):
    code = "OC-2002"


class ConflictError(BusinessError):
    code = "OC-2003"
    http_status = 409

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message, code=code or "OC-2003")


class IngressError(BusinessError):
    code = "OC-3001"


class GraphUnavailable(SystemError):
    code = "OC-4001"
    http_status = 503

    def __init__(self, message: str = "") -> None:
        super().__init__(message, code="OC-4001")


class StructuredOutputError(BusinessError):
    code = "OC-3101"
