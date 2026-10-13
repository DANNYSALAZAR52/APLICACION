"""Hash de contraseñas con Argon2id (`PasswordHasherPort`)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    """Argon2id con los parámetros por defecto de argon2-cffi (RFC 9106, perfil de baja memoria)."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher()  # Argon2id por defecto
        # Hash de una contraseña inalcanzable: se usa para igualar el tiempo cuando el usuario
        # no existe y así no revelar su existencia por la latencia.
        self._dummy_hash = self._hasher.hash("contraseña-inexistente-para-igualar-tiempos")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> None:
        self.verify(self._dummy_hash, password)
