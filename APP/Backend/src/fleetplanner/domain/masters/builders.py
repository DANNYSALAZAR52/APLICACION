"""Del maestro editable al objeto de dominio y de vuelta.

Los constructores de dominio son la ÚNICA fuente de validez: si el objeto se puede construir, el
dato es válido para los cálculos. Aquí solo se traducen unidades (porcentaje 0–100 ↔ fracción,
HH:MM ↔ minutos) y se revisan las referencias entre maestros.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from fleetplanner.domain.capacity.models import Corridor, VehicleType
from fleetplanner.domain.masters.schema import EntitySpec, FieldIssue
from fleetplanner.domain.routing.models import (
    Customer,
    Order,
    RoutingVehicle,
    VehicleKind,
)
from fleetplanner.domain.routing.time_window import TimeWindow, format_clock, parse_clock
from fleetplanner.domain.shared.errors import InvalidValueError
from fleetplanner.domain.shared.percentage import Percentage

Values = Mapping[str, object]


class Lookups(Protocol):
    """Consulta de existencia de otros maestros (para validar referencias)."""

    def exists(self, entity: str, key: str) -> bool: ...


# ----------------------------------------------------------------- hacia el dominio
def build_vehicle_type(v: Values) -> VehicleType:
    return VehicleType(
        name=str(v["name"]),
        capacity_t=float(v["capacity_t"]),  # type: ignore[arg-type]
        capacity_m3=float(v["capacity_m3"]),  # type: ignore[arg-type]
        pallets=int(v["pallets"]),  # type: ignore[call-overload]
        fixed_cost_month=float(v["fixed_cost_month"]),  # type: ignore[arg-type]
        variable_cost_per_km=float(v["variable_cost_per_km"]),  # type: ignore[arg-type]
        third_party_daily_rate=float(v["third_party_daily_rate"]),  # type: ignore[arg-type]
    )


def build_corridor(v: Values) -> Corridor:
    return Corridor(
        code=str(v["code"]),
        name=str(v["name"]),
        assigned_vehicle_type=str(v["assigned_vehicle_type"]),
        one_way_km=float(v["one_way_km"]),  # type: ignore[arg-type]
        average_speed_kmh=float(v["average_speed_kmh"]),  # type: ignore[arg-type]
        operating_hours=float(v["operating_hours"]),  # type: ignore[arg-type]
        loading_h=float(v["loading_h"]),  # type: ignore[arg-type]
        dock_wait_h=float(v["dock_wait_h"]),  # type: ignore[arg-type]
        stops=int(v["stops"]),  # type: ignore[call-overload]
        minutes_per_stop=float(v["minutes_per_stop"]),  # type: ignore[arg-type]
        customer_wait_h=float(v["customer_wait_h"]),  # type: ignore[arg-type]
        fill=Percentage.from_percent(float(v["fill"])),  # type: ignore[arg-type]
        backhaul=Percentage.from_percent(float(v["backhaul"])),  # type: ignore[arg-type]
    )


def build_customer(v: Values) -> Customer:
    """Valida el cliente completo; informa TODOS los problemas a la vez (criterio 11)."""
    return Customer.create(
        code=str(v["code"]),
        name=str(v["name"]),
        address=str(v.get("address", "")),
        lat=float(v["lat"]),  # type: ignore[arg-type]
        lon=float(v["lon"]),  # type: ignore[arg-type]
        window_start_min=parse_clock(str(v["window_start"])),
        window_end_min=parse_clock(str(v["window_end"])),
        service_minutes=float(v["service_minutes"]),  # type: ignore[arg-type]
        restrictions=(str(v["restrictions"]),) if v.get("restrictions") else (),
    )


def build_routing_vehicle(v: Values) -> RoutingVehicle:
    return RoutingVehicle(
        id=str(v["id"]),
        plate=str(v["plate"]),
        vehicle_type=str(v["vehicle_type"]),
        capacity_kg=float(v["capacity_kg"]),  # type: ignore[arg-type]
        kind=VehicleKind(str(v["kind"])),
        gps_id=str(v.get("gps_id", "")),
    )


def build_order(v: Values) -> Order:
    window = TimeWindow(parse_clock(str(v["window_start"])), parse_clock(str(v["window_end"])))
    return Order(
        id=str(v["id"]),
        customer_code=str(v["customer_code"]),
        kg=float(v["kg"]),  # type: ignore[arg-type]
        m3=float(v["m3"]),  # type: ignore[arg-type]
        window=window,
        priority=int(str(v["priority"])),
    )


BUILDERS = {
    "vehicle_type": build_vehicle_type,
    "corridor": build_corridor,
    "customer": build_customer,
    "vehicle": build_routing_vehicle,
    "order": build_order,
}


def validate_domain(entity: EntitySpec, values: Values) -> list[FieldIssue]:
    """Ejecuta el constructor de dominio; su mensaje (en español) se devuelve como problema."""
    builder = BUILDERS.get(entity.name)
    if builder is None:
        return []
    try:
        builder(values)
    except InvalidValueError as error:
        return [FieldIssue("*", str(error))]
    return []


def validate_references(entity: EntitySpec, values: Values, lookups: Lookups) -> list[FieldIssue]:
    """Las referencias a otros maestros deben existir."""
    refs: list[tuple[str, str, str]] = []  # (campo, entidad referenciada, etiqueta)
    name = entity.name
    if name == "corridor":
        refs = [("assigned_vehicle_type", "vehicle_type", "El tipo de vehículo")]
    elif name == "compatibility":
        refs = [
            ("corridor_code", "corridor", "La ruta"),
            ("vehicle_type", "vehicle_type", "El tipo de vehículo"),
        ]
    elif name == "fleet":
        refs = [("vehicle_type", "vehicle_type", "El tipo de vehículo")]
    elif name == "daily_demand":
        refs = [("corridor_code", "corridor", "La ruta")]
    elif name == "order":
        refs = [("customer_code", "customer", "El cliente")]
    issues: list[FieldIssue] = []
    for field, target, label in refs:
        value = values.get(field)
        if value is not None and not lookups.exists(target, str(value)):
            issues.append(FieldIssue(field, f"{label} «{value}» no existe; créelo primero."))
    return issues


# ------------------------------------------------------------------ desde el dominio
def values_of_vehicle_type(t: VehicleType) -> dict[str, object]:
    return {
        "name": t.name,
        "capacity_t": t.capacity_t,
        "capacity_m3": t.capacity_m3,
        "pallets": t.pallets,
        "fixed_cost_month": t.fixed_cost_month,
        "variable_cost_per_km": t.variable_cost_per_km,
        "third_party_daily_rate": t.third_party_daily_rate,
    }


def values_of_corridor(c: Corridor) -> dict[str, object]:
    return {
        "code": c.code,
        "name": c.name,
        "assigned_vehicle_type": c.assigned_vehicle_type,
        "one_way_km": c.one_way_km,
        "average_speed_kmh": c.average_speed_kmh,
        "operating_hours": c.operating_hours,
        "loading_h": c.loading_h,
        "dock_wait_h": c.dock_wait_h,
        "stops": c.stops,
        "minutes_per_stop": c.minutes_per_stop,
        "customer_wait_h": c.customer_wait_h,
        "fill": round(c.fill.percent, 6),
        "backhaul": round(c.backhaul.percent, 6),
    }


def values_of_customer(c: Customer) -> dict[str, object]:
    values: dict[str, object] = {
        "code": c.code,
        "name": c.name,
        "lat": c.point.lat,
        "lon": c.point.lon,
        "service_minutes": c.service_minutes,
        "window_start": format_clock(c.window.start_min),
        "window_end": format_clock(c.window.end_min),
    }
    if c.address:
        values["address"] = c.address
    if c.restrictions:
        values["restrictions"] = ", ".join(c.restrictions)
    return values


def values_of_vehicle(v: RoutingVehicle) -> dict[str, object]:
    values: dict[str, object] = {
        "id": v.id,
        "plate": v.plate,
        "vehicle_type": v.vehicle_type,
        "capacity_kg": v.capacity_kg,
        "kind": v.kind.value,
    }
    if v.gps_id:
        values["gps_id"] = v.gps_id
    return values


def values_of_order(o: Order) -> dict[str, object]:
    return {
        "id": o.id,
        "customer_code": o.customer_code,
        "kg": o.kg,
        "m3": o.m3,
        "window_start": format_clock(o.window.start_min),
        "window_end": format_clock(o.window.end_min),
        "priority": str(o.priority),
    }
