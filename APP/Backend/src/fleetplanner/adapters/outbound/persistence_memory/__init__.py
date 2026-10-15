"""Persistencia en memoria (DEMO-ONLY).

Sustituye a los adaptadores SQLAlchemy/PostgreSQL, que están descritos y comentados en
el paquete ``persistence_sql``. Ver ``docs/DEUDA_DEMO.md``.
"""

from fleetplanner.adapters.outbound.persistence_memory.capacity_results import (
    InMemoryCapacityResultRepository,
)
from fleetplanner.adapters.outbound.persistence_memory.control_plane import (
    InMemoryAuditLog,
    InMemoryRateLimiter,
    InMemoryRefreshTokenStore,
    InMemoryTenantRegistry,
    InMemoryTenantWorkspaceProvider,
    InMemoryUserRepository,
)
from fleetplanner.adapters.outbound.persistence_memory.master_data import (
    InMemoryMasterDataStore,
)
from fleetplanner.adapters.outbound.persistence_memory.ml_registry import (
    InMemoryModelRegistry,
)
from fleetplanner.adapters.outbound.persistence_memory.routing_state import (
    InMemoryRoutingRepository,
)

__all__ = [
    "InMemoryAuditLog",
    "InMemoryCapacityResultRepository",
    "InMemoryMasterDataStore",
    "InMemoryModelRegistry",
    "InMemoryRateLimiter",
    "InMemoryRefreshTokenStore",
    "InMemoryRoutingRepository",
    "InMemoryTenantRegistry",
    "InMemoryTenantWorkspaceProvider",
    "InMemoryUserRepository",
]
