"""Datos sintéticos de demostración (DEMO-ONLY)."""

from fleetplanner.adapters.outbound.demo_data.capacity_dataset import (
    DEMO_LABEL,
    DemoCapacityInputsReader,
)
from fleetplanner.adapters.outbound.demo_data.profiles import (
    DEMO_A_SLUG,
    DEMO_B_SLUG,
    capacity_reader_for_slug,
)

__all__ = [
    "DEMO_A_SLUG",
    "DEMO_B_SLUG",
    "DEMO_LABEL",
    "DemoCapacityInputsReader",
    "capacity_reader_for_slug",
]
