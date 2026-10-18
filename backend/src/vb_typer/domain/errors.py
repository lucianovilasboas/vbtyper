"""Erros de domínio e seu mapeamento para HTTP."""

from __future__ import annotations


class DomainError(Exception):
    """Erro esperado, seguro para devolver ao cliente."""

    status_code = 400
    code = "invalid_request"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class UnauthorizedError(DomainError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(DomainError):
    status_code = 403
    code = "forbidden"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class AudioTooLargeError(DomainError):
    status_code = 413
    code = "audio_too_large"


class UnsupportedMediaTypeError(DomainError):
    status_code = 415
    code = "unsupported_media_type"


class InvalidModelError(DomainError):
    status_code = 422
    code = "invalid_model"


class ApiKeyMissingError(DomainError):
    status_code = 503
    code = "api_key_missing"


class ProviderError(DomainError):
    status_code = 502
    code = "provider_error"


class InvalidAudioError(DomainError):
    status_code = 400
    code = "invalid_audio"
