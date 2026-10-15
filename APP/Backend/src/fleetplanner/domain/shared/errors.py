"""Errores de dominio con mensajes en español orientados a quien debe corregir el dato."""


class DomainError(Exception):
    """Error base del dominio."""


class InvalidValueError(DomainError):
    """Un valor viola una invariante del dominio."""


class InsufficientDataError(DomainError):
    """No hay datos suficientes para calcular de forma confiable."""


class AuthenticationError(DomainError):
    """Credenciales o sesión inválidas. El mensaje es deliberadamente genérico."""


class PermissionDeniedError(DomainError):
    """La identidad autenticada no tiene permiso para la operación."""


class NotFoundError(DomainError):
    """El recurso no existe o no es visible para la identidad (no se distingue)."""


class TenantSuspendedError(DomainError):
    """La empresa está suspendida: se bloquean solicitudes y trabajos nuevos."""


class RateLimitedError(DomainError):
    """Se superó el límite de intentos permitido."""


class ConflictError(DomainError):
    """La operación choca con el estado actual (p. ej. identificador repetido)."""


class ArtifactIntegrityError(DomainError):
    """Un artefacto guardado no coincide con el hash registrado: no se carga."""
