"""Datos sintéticos de demostración (DEMO-ONLY)."""

from fleetplanner.adapters.outbound.demo_data.capacity_dataset import (
    DEMO_LABEL,
    DemoCapacityInputsReader,
)
from fleetplanner.adapters.outbound.demo_data.ml_history import (
    SEEDED_PATTERNS,
    DemoHistoryReader,
    history_reader_for_slug,
)
from fleetplanner.adapters.outbound.demo_data.profiles import (
    DEMO_A_SLUG,
    DEMO_B_SLUG,
    capacity_reader_for_slug,
)
from fleetplanner.adapters.outbound.demo_data.routing_dataset import (
    DemoRoutingInputsReader,
    routing_reader_for_slug,
)

__all__ = [
    "DEMO_A_SLUG",
    "DEMO_B_SLUG",
    "DEMO_LABEL",
    "SEEDED_PATTERNS",
    "DemoCapacityInputsReader",
    "DemoHistoryReader",
    "DemoRoutingInputsReader",
    "capacity_reader_for_slug",
    "history_reader_for_slug",
    "routing_reader_for_slug",
]
