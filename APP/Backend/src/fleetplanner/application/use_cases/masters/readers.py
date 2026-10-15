"""Lectores que alimentan los cálculos con los maestros EDITADOS de la empresa.

Reemplazan a los lectores sintéticos fijos: lo que el administrador cambia se refleja en la
siguiente corrida de capacidad y en el siguiente día operativo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date

from fleetplanner.application.dto.capacity import CapacityInputs
from fleetplanner.application.ports.outbound.routing import RoutingDataset
from fleetplanner.application.use_cases.masters.parameters import (
    capacity_parameters,
    initial_values,
    routing_params,
)
from fleetplanner.application.use_cases.masters.service import MasterDataService
from fleetplanner.domain.capacity.models import CompatibilityMatrix, DemandSeries
from fleetplanner.domain.masters.builders import (
    build_corridor,
    build_customer,
    build_order,
    build_routing_vehicle,
    build_vehicle_type,
    values_of_corridor,
    values_of_customer,
    values_of_order,
    values_of_vehicle,
    values_of_vehicle_type,
)
from fleetplanner.domain.masters.catalog import (
    COMPATIBILITY,
    CORRIDOR,
    CUSTOMER,
    DAILY_DEMAND,
    FLEET,
    ORDER,
    VEHICLE,
    VEHICLE_TYPE,
)


class StoreCapacityInputsReader:
    """`CapacityInputsReader` sobre los maestros editados; lo no editable viene de ``base``."""

    def __init__(self, service: MasterDataService, base: CapacityInputs) -> None:
        self._service = service
        self._base = base

    def load(self) -> CapacityInputs:
        store = self._service.store
        types = [build_vehicle_type(r) for r in store.rows(VEHICLE_TYPE.name)]
        corridors = [build_corridor(r) for r in store.rows(CORRIDOR.name)]
        codes = {c.code for c in corridors}
        observations: dict[str, dict[date, float]] = defaultdict(dict)
        for r in store.rows(DAILY_DEMAND.name):
            observations[str(r["corridor_code"])][date.fromisoformat(str(r["date"]))] = float(
                r["tons"]  # type: ignore[arg-type]
            )
        demand = {code: DemandSeries(code, observations.get(code, {})) for code in sorted(codes)}
        scenarios = [
            replace(
                s,
                route_adjustments={k: v for k, v in s.route_adjustments.items() if k in codes},
                new_volume_t={k: v for k, v in s.new_volume_t.items() if k in codes},
            )
            for s in self._base.scenarios
        ]
        return CapacityInputs(
            vehicle_types={t.name: t for t in types},
            corridors=sorted(corridors, key=lambda c: c.code),
            compatibility=CompatibilityMatrix.of(
                (str(r["corridor_code"]), str(r["vehicle_type"]))
                for r in store.rows(COMPATIBILITY.name)
            ),
            demand=demand,
            current_fleet={str(r["vehicle_type"]): int(r["count"]) for r in store.rows(FLEET.name)},  # type: ignore[call-overload]
            parameters=capacity_parameters(self._service.effective_values(), self._base.parameters),
            scenarios=scenarios,
        )


class StoreRoutingInputsReader:
    """`RoutingInputsReader` sobre los maestros editados."""

    def __init__(self, service: MasterDataService, base: RoutingDataset) -> None:
        self._service = service
        self._base = base

    def read(self) -> RoutingDataset:
        store = self._service.store
        customers = sorted(
            (build_customer(r) for r in store.rows(CUSTOMER.name)), key=lambda c: c.code
        )
        orders = sorted((build_order(r) for r in store.rows(ORDER.name)), key=lambda o: o.id)
        vehicles = sorted(
            (build_routing_vehicle(r) for r in store.rows(VEHICLE.name)), key=lambda v: v.id
        )
        return RoutingDataset(
            depot=self._base.depot,
            customers=tuple(customers),
            orders=tuple(orders),
            vehicles=tuple(vehicles),
            params=routing_params(self._service.effective_values(), self._base.params),
        )


def seed_master_data(
    service: MasterDataService, capacity: CapacityInputs, routing: RoutingDataset
) -> None:
    """Carga los datos sintéticos iniciales en el almacén de la empresa (una sola vez)."""
    store = service.store
    for t in capacity.vehicle_types.values():
        store.put(VEHICLE_TYPE.name, t.name, values_of_vehicle_type(t))
    for c in capacity.corridors:
        store.put(CORRIDOR.name, c.code, values_of_corridor(c))
    for corridor_code, vehicle_type in sorted(capacity.compatibility.allowed):
        row: dict[str, object] = {"corridor_code": corridor_code, "vehicle_type": vehicle_type}
        store.put(COMPATIBILITY.name, COMPATIBILITY.key_of(row), row)
    for vehicle_type, count in capacity.current_fleet.items():
        store.put(FLEET.name, vehicle_type, {"vehicle_type": vehicle_type, "count": count})
    for series in capacity.demand.values():
        for day, tons in series.observations.items():
            demand_row: dict[str, object] = {
                "corridor_code": series.corridor_code,
                "date": day.isoformat(),
                "tons": tons,
            }
            store.put(DAILY_DEMAND.name, DAILY_DEMAND.key_of(demand_row), demand_row)
    for customer in routing.customers:
        store.put(CUSTOMER.name, customer.code, values_of_customer(customer))
    for vehicle in routing.vehicles:
        store.put(VEHICLE.name, vehicle.id, values_of_vehicle(vehicle))
    for order in routing.orders:
        store.put(ORDER.name, order.id, values_of_order(order))
    for key, value in initial_values(capacity.parameters, routing.params).items():
        service.seed_parameter(key, value)
