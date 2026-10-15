"""Configuración validada al arranque, con fallo seguro si falta un secreto obligatorio."""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field

LOCAL = "local"
MIN_DEMO_PASSWORD_LENGTH = 12


class ConfigurationError(RuntimeError):
    """Configuración inválida o secreto obligatorio ausente."""


@dataclass(frozen=True)
class Settings:
    environment: str
    jwt_signing_key: str = field(repr=False)  # nunca se imprime
    ephemeral_signing_key: bool
    allowed_origins: tuple[str, ...]
    host: str = "127.0.0.1"
    port: int = 8000
    frontend_dist: str | None = None
    demo_password: str | None = field(default=None, repr=False)
    demo_superadmin_password: str | None = field(default=None, repr=False)

    @property
    def is_local(self) -> bool:
        return self.environment == LOCAL


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Lee la configuración del entorno.

    * ``FLEETPLANNER_ENV`` (por defecto ``local``).
    * ``JWT_SIGNING_KEY`` es obligatoria fuera de ``local``; en ``local`` se genera una clave
      efímera (DEMO-ONLY: las sesiones no sobreviven a un reinicio).
    * ``ALLOWED_ORIGINS`` lista blanca CORS separada por comas.
    * ``HOST`` / ``PORT`` (por defecto 127.0.0.1:8000). Un hospedaje define ``PORT``.
    * ``FRONTEND_DIST`` carpeta con la interfaz compilada para servirla desde la misma API.
    * ``DEMO_PASSWORD`` / ``DEMO_SUPERADMIN_PASSWORD`` (opcionales, DEMO-ONLY): contraseñas
      fijas de los usuarios sembrados para mostrar la demo a terceros. Si faltan, se generan
      aleatorias en cada arranque. Nunca se imprimen ni se guardan en el repositorio.
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
    demo_password = _optional_password(env, "DEMO_PASSWORD")
    superadmin_password = _optional_password(env, "DEMO_SUPERADMIN_PASSWORD")
    if demo_password and superadmin_password and demo_password == superadmin_password:
        raise ConfigurationError("DEMO_SUPERADMIN_PASSWORD debe ser distinta de DEMO_PASSWORD.")
    return Settings(
        environment,
        key,
        ephemeral,
        origins,
        host=env.get("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_port(env.get("PORT", "8000")),
        frontend_dist=env.get("FRONTEND_DIST", "").strip() or None,
        demo_password=demo_password,
        demo_superadmin_password=superadmin_password,
    )


def _port(raw: str) -> int:
    try:
        port = int(raw.strip())
    except ValueError as error:
        raise ConfigurationError("PORT debe ser un número entero.") from error
    if not 1 <= port <= 65535:
        raise ConfigurationError("PORT debe estar entre 1 y 65535.")
    return port


def _optional_password(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    if not value:
        return None
    if len(value) < MIN_DEMO_PASSWORD_LENGTH:
        raise ConfigurationError(
            f"{name} debe tener al menos {MIN_DEMO_PASSWORD_LENGTH} caracteres."
        )
    return value
