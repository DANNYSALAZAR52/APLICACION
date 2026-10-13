"""Política de contraseñas y bloqueo progresivo por intentos fallidos."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fleetplanner.domain.shared.errors import InvalidValueError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def validate_password_policy(password: str) -> None:
    """Exige longitud 12–128 y al menos una letra y un número."""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidValueError(
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} "
            "caracteres."
        )
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise InvalidValueError("La contraseña debe incluir al menos una letra y un número.")


def generate_password(length: int = 18) -> str:
    """Contraseña aleatoria criptográficamente segura que cumple la política."""
    if length < MIN_PASSWORD_LENGTH:
        raise InvalidValueError("La longitud solicitada es menor que la mínima permitida.")
    while True:
        candidate = secrets.token_urlsafe(length)[:length]
        try:
            validate_password_policy(candidate)
        except InvalidValueError:
            continue
        return candidate


class LockoutPolicy:
    """Retardo progresivo: tras ``threshold`` fallos se bloquea y el bloqueo se duplica.

    Con umbral 5 y base 30 s: 5.º fallo → 30 s, 6.º → 60 s, 7.º → 120 s... hasta ``max_lock``.
    """

    def __init__(
        self,
        threshold: int = 5,
        base: timedelta = timedelta(seconds=30),
        max_lock: timedelta = timedelta(minutes=15),
    ) -> None:
        if threshold < 1:
            raise ValueError("El umbral de bloqueo debe ser al menos 1.")
        self._threshold = threshold
        self._base = base
        self._max = max_lock

    def locked_until_after_failure(self, failed_attempts: int, now: datetime) -> datetime | None:
        """Instante hasta el que se bloquea tras acumular ``failed_attempts`` fallos."""
        if failed_attempts < self._threshold:
            return None
        steps = failed_attempts - self._threshold
        lock = min(self._base * (1 << min(steps, 20)), self._max)
        return now + lock

    @staticmethod
    def is_locked(locked_until: datetime | None, now: datetime) -> bool:
        return locked_until is not None and now < locked_until
