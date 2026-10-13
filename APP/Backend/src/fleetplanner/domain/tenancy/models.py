"""Tenants, usuarios y la identidad autenticada (`Principal`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from fleetplanner.domain.shared.errors import InvalidValueError

_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Role(StrEnum):
    MANAGEMENT = "management"  # Gerencia de operaciones
    DISPATCHER = "dispatcher"  # Despachador
    DRIVER = "driver"  # Conductor
    TENANT_ADMIN = "tenant_admin"  # Administrador del tenant
    SUPER_ADMIN = "super_admin"  # Superadministrador (sin tenant)


@dataclass(frozen=True)
class TenantId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise InvalidValueError("El identificador de empresa no puede estar vacío.")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Tenant:
    """Empresa cliente. No contiene secretos ni cadenas de conexión."""

    id: TenantId
    slug: str
    name: str
    status: TenantStatus
    created_at: datetime

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.slug) or len(self.slug) > 40:
            raise InvalidValueError(
                "El identificador corto de la empresa solo admite minúsculas, números y "
                "guiones (máximo 40 caracteres)."
            )
        if not self.name.strip() or len(self.name) > 120:
            raise InvalidValueError("El nombre de la empresa es obligatorio (máximo 120).")

    @property
    def is_active(self) -> bool:
        return self.status is TenantStatus.ACTIVE

    def suspended(self) -> Tenant:
        return replace(self, status=TenantStatus.SUSPENDED)

    def reactivated(self) -> Tenant:
        return replace(self, status=TenantStatus.ACTIVE)


@dataclass(frozen=True)
class User:
    """Usuario. Un superadministrador no pertenece a ningún tenant (``tenant_id`` es None)."""

    id: str
    tenant_id: TenantId | None
    username: str
    display_name: str
    role: Role
    password_hash: str
    active: bool = True
    failed_attempts: int = 0
    locked_until: datetime | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.username.strip():
            raise InvalidValueError("El nombre de usuario es obligatorio.")
        if self.role is Role.SUPER_ADMIN and self.tenant_id is not None:
            raise InvalidValueError("El superadministrador no puede pertenecer a una empresa.")
        if self.role is not Role.SUPER_ADMIN and self.tenant_id is None:
            raise InvalidValueError("Todo usuario, salvo el superadministrador, requiere empresa.")


@dataclass(frozen=True)
class Principal:
    """Identidad autenticada y verificada contra el registro central.

    Es la ÚNICA fuente confiable del tenant y el rol. Nunca se construye con datos que envíe el
    cliente en cuerpo, query o cabeceras: solo desde un token validado y el usuario guardado.
    """

    user_id: str
    username: str
    role: Role
    tenant_id: TenantId | None
    tenant_slug: str | None
    tenant_name: str | None = None
