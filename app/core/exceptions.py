from fastapi import HTTPException


class AurynixError(Exception):
    """Base exception for all application errors."""

    status_code: int = 500
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)

    def to_http_exception(self) -> HTTPException:
        return HTTPException(status_code=self.status_code, detail=self.detail)


class NotFoundError(AurynixError):
    status_code = 404
    detail = "Resource not found."


class ConflictError(AurynixError):
    status_code = 409
    detail = "Resource already exists."


class AuthenticationError(AurynixError):
    status_code = 401
    detail = "Authentication failed."


class PermissionDeniedError(AurynixError):
    status_code = 403
    detail = "Permission denied."


class ValidationError(AurynixError):
    status_code = 422
    detail = "Validation error."


class ExternalServiceError(AurynixError):
    status_code = 502
    detail = "External service unavailable."


class DocumentProcessingError(AurynixError):
    status_code = 422
    detail = "Document processing failed."
