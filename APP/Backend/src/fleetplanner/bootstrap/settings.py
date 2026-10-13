"""Configuración validada al arranque, con fallo seguro si falta un secreto obligatorio."""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field

LOCAL = "local"


class ConfigurationError(RuntimeError):
    """Configuración inválida o secreto obligatorio ausente."""


@dataclass(frozen=True)
class Settings:
    environment: str
    jwt_signing_key: str = field(repr=False)  # nunca se imprime
    ephemeral_signing_key: bool
    allowed_origins: tuple[str, ...]

    @property
    def is_local(self) -> bool:
        return self.environment == LOCAL


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Lee la configuración del entorno.

    * ``FLEETPLANNER_ENV`` (por defecto ``local``).
    * ``JWT_SIGNING_KEY`` es obligatoria fuera de ``local``; en ``local`` se genera una clave
      efímera (DEMO-ONLY: las sesiones no sobreviven a un reinicio).
    * ``ALLOWED_ORIGINS`` lista blanca CORS separada por comas.
    """
    env = dict(os.environ if environ is None else environ)
    environment = env.get("FLEETPLANNER_ENV", LOCAL).strip().lower()
    key = env.get("JWT_SIGNING_KEY", "").strip()
    ephemeral = False
    if not key:
        if environment != LOCAL:
            raise ConfigurationError(
                "Falta JWT_SIGNING_KEY. Fuera del entorno local es obligatoria; la aplicación "
                "no arranca sin ella."
            )
        key = secrets.token_urlsafe(48)
        ephemeral = True
    if len(key.encode()) < 32:
        raise ConfigurationError("JWT_SIGNING_KEY debe tener al menos 32 bytes.")
    origins = tuple(
        o.strip()
        for o in env.get("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(
            ","
        )
        if o.strip()
    )
    if "*" in origins:
        raise ConfigurationError("ALLOWED_ORIGINS no admite '*': use una lista blanca explícita.")
    return Settings(environment, key, ephemeral, origins)
