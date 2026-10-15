"""Confirmación de entregas y novedades del conductor."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ConfirmationSource(StrEnum):
    GEOFENCE = "geofence"
    DRIVER = "driver"


@dataclass(frozen=True)
class DeliveryConfirmation:
    """Entrega confirmada por geocerca o por el conductor."""

    order_id: str
    minute: float
    source: ConfirmationSource
    by: str = ""


class IncidentKind(StrEnum):
    CUSTOMER_ABSENT = "customer_absent"
    ACCESS_BLOCKED = "access_blocked"
    DAMAGED_GOODS = "damaged_goods"
    VEHICLE_ISSUE = "vehicle_issue"
    OTHER = "other"


@dataclass(frozen=True)
class DriverReport:
    """Novedad reportada por el conductor. No cambia el plan: avisa al despachador."""

    id: str
    vehicle_id: str
    minute: float
    kind: IncidentKind
    detail: str
    by: str
    order_id: str | None = None
