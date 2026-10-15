"""Armado del servicio de maestros (sembrado con datos sintéticos) para pruebas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fleetplanner.adapters.outbound.clock import FixedClock, SimulatedClock
from fleetplanner.adapters.outbound.demo_data import (
    DemoRoutingInputsReader,
    capacity_reader_for_slug,
)
from fleetplanner.adapters.outbound.demo_data.routing_dataset import RoutingProfile
from fleetplanner.adapters.outbound.persistence_memory import InMemoryMasterDataStore
from fleetplanner.application.dto.capacity import CapacityInputs
from fleetplanner.application.ports.outbound.routing import RoutingDataset
from fleetplanner.application.use_cases.masters.readers import (
    StoreCapacityInputsReader,
    StoreRoutingInputsReader,
    seed_master_data,
)
from fleetplanner.application.use_cases.masters.service import MasterDataService
from fleetplanner.bootstrap.container import (
    RoutingContainer,
    build_capacity_container,
    build_routing_container,
)
from routing_flow_helpers import DAY, HeuristicSolver

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=DAY.tzinfo)


@dataclass
class Masters:
    service: MasterDataService
    clock: FixedClock
    capacity_base: CapacityInputs
    routing_base: RoutingDataset

    def capacity_reader(self) -> StoreCapacityInputsReader:
        return StoreCapacityInputsReader(self.service, self.capacity_base)

    def routing(self) -> RoutingContainer:
        reader = StoreRoutingInputsReader(self.service, self.routing_base)
        return build_routing_container(reader, HeuristicSolver(), SimulatedClock(DAY))

    def dashboard(self):  # type: ignore[no-untyped-def]
        container = build_capacity_container(reader=self.capacity_reader(), clock=self.clock)
        return container.dashboard.execute()


def make_masters(customers: int = 8) -> Masters:
    clock = FixedClock(NOW)
    capacity = capacity_reader_for_slug("empresa-demo-b").load()
    routing = DemoRoutingInputsReader(
        RoutingProfile(seed=3, customers=customers, active_vehicles=2)
    ).read()
    service = MasterDataService(
        InMemoryMasterDataStore(), clock, capacity.parameters, routing.params
    )
    seed_master_data(service, capacity, routing)
    return Masters(service, clock, capacity, routing)
