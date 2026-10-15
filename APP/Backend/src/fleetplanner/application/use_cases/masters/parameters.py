"""Parámetros vigentes → objetos que consumen los cálculos de capacidad y de ruteo."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from fleetplanner.application.dto.capacity import CapacityParameters
from fleetplanner.domain.capacity.models import OeeFactors
from fleetplanner.domain.routing.models import RoutingParams
from fleetplanner.domain.routing.time_window import format_clock, parse_clock
from fleetplanner.domain.shared.percentage import Percentage


def _f(values: Mapping[str, object], key: str) -> float:
    return float(values[key])  # type: ignore[arg-type]


def capacity_parameters(
    values: Mapping[str, object], base: CapacityParameters
) -> CapacityParameters:
    """Aplica los parámetros editables sobre la base (lo no editable se conserva)."""
    return replace(
        base,
        design_percentile=Percentage.from_percent(_f(values, "design_percentile")),
        reserve=Percentage.from_percent(_f(values, "reserve")),
        days_per_month=int(_f(values, "days_per_month")),
        window_days=int(_f(values, "window_days")),
        oee=OeeFactors(
            Percentage.from_percent(_f(values, "oee_availability")),
            Percentage.from_percent(_f(values, "oee_utilization")),
            Percentage.from_percent(_f(values, "oee_performance")),
        ),
    )


def routing_params(values: Mapping[str, object], base: RoutingParams) -> RoutingParams:
    return replace(
        base,
        departure_min=float(parse_clock(str(values["departure"]))),
        shift_end_min=float(parse_clock(str(values["shift_end"]))),
        max_fill=_f(values, "max_fill") / 100.0,
        service_kg_per_min=_f(values, "service_kg_per_min"),
        weight_travel=_f(values, "weight_travel"),
        weight_wait=_f(values, "weight_wait"),
        weight_delay=_f(values, "weight_delay"),
        weight_overtime=_f(values, "weight_overtime"),
        transshipment_min=_f(values, "transshipment_min"),
        reload_min=_f(values, "reload_min"),
        reserve_activation_cost=_f(values, "reserve_activation_cost"),
        risk_margin_min=_f(values, "risk_margin_min"),
    )


def initial_values(capacity: CapacityParameters, routing: RoutingParams) -> dict[str, object]:
    """Valores iniciales de todos los parámetros editables, tomados de los datos base."""
    return {
        "design_percentile": round(capacity.design_percentile.percent, 6),
        "reserve": round(capacity.reserve.percent, 6),
        "days_per_month": capacity.days_per_month,
        "window_days": capacity.window_days,
        "oee_availability": round(capacity.oee.availability.percent, 6),
        "oee_utilization": round(capacity.oee.utilization.percent, 6),
        "oee_performance": round(capacity.oee.performance.percent, 6),
        "max_fill": round(routing.max_fill * 100.0, 6),
        "service_kg_per_min": routing.service_kg_per_min,
        "weight_travel": routing.weight_travel,
        "weight_wait": routing.weight_wait,
        "weight_delay": routing.weight_delay,
        "weight_overtime": routing.weight_overtime,
        "transshipment_min": routing.transshipment_min,
        "reload_min": routing.reload_min,
        "reserve_activation_cost": routing.reserve_activation_cost,
        "risk_margin_min": routing.risk_margin_min,
        "departure": format_clock(routing.departure_min),
        "shift_end": format_clock(routing.shift_end_min),
    }
