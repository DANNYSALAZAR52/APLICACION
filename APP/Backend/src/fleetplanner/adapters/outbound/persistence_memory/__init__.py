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

__all__ = [
    "InMemoryAuditLog",
    "InMemoryCapacityResultRepository",
    "InMemoryRateLimiter",
    "InMemoryRefreshTokenStore",
    "InMemoryTenantRegistry",
    "InMemoryTenantWorkspaceProvider",
    "InMemoryUserRepository",
]
