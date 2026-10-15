"""Tarea programada de seguimiento: por empresa, sin mezclar datos y tolerante a fallos."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from test_routing_flow import closure_case

from fleetplanner.adapters.outbound.persistence_memory import (
    InMemoryAuditLog,
    InMemoryTenantRegistry,
    InMemoryTenantWorkspaceProvider,
)
from fleetplanner.application.use_cases.routing.scheduled import (
    SCHEDULER_ACTOR,
    ScheduledTracking,
)
from fleetplanner.domain.routing.events import Closure
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.tenancy.models import Tenant, TenantId, TenantStatus

NOW = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)


class Clock:
    def now(self) -> datetime:
        return NOW


def tenant(slug: str) -> Tenant:
    return Tenant(TenantId(f"t-{slug}"), slug, slug.upper(), TenantStatus.ACTIVE, NOW)


class Catalog:
    def __init__(self, *entries):  # type: ignore[no-untyped-def]
        self._entries = list(entries)

    def active_workspaces(self):  # type: ignore[no-untyped-def]
        return self._entries


def late_flow():  # type: ignore[no-untyped-def]
    """Plan con un cierre que nadie ha tratado: el seguimiento debería proponer re-secuenciar."""
    flow = closure_case()
    flow.at(6, 15)
    flow.ws.core.repo.add_closure(
        Closure("EXT-1", "Cierre externo", GeoPoint(4.678, -74.155), 1.0, 3.0, 375.0, 675.0)
    )
    return flow


def run(flow, *, paused: bool):  # type: ignore[no-untyped-def]
    clock = flow.container.clock
    if not paused:
        clock.set_speed(1.0)
        clock.resume()
    audit = InMemoryAuditLog()
    catalog = Catalog((tenant("a"), SimpleNamespace(routing=flow.ws)))
    created = ScheduledTracking(catalog, audit, Clock()).execute()
    return created, audit


class TestScheduledTracking:
    def test_a_paused_day_is_skipped_because_no_time_passes(self) -> None:
        flow = late_flow()
        created, audit = run(flow, paused=True)
        assert created == 0 and audit.list_events(None) == []
        assert flow.ws.core.repo.proposals() == []

    def test_a_running_day_gets_a_proposal_and_the_audit_names_the_system_and_tenant(self) -> None:
        flow = late_flow()
        created, audit = run(flow, paused=False)
        assert created == 1
        (event,) = audit.list_events(None)
        assert event.action == "routing.proposal.auto"
        assert event.actor_username == SCHEDULER_ACTOR and event.actor_user_id is None
        assert event.tenant_id == "t-a"
        proposal = flow.ws.core.repo.proposals()[0]
        assert proposal.status.value == "pending"
        assert flow.ws.core.repo.active_plan().version == 1  # propone, no aplica

    def test_it_does_not_repeat_while_the_proposal_is_pending(self) -> None:
        flow = late_flow()
        run(flow, paused=False)
        flow.container.clock.resume()
        assert (
            ScheduledTracking(
                Catalog((tenant("a"), SimpleNamespace(routing=flow.ws))),
                InMemoryAuditLog(),
                Clock(),
            ).execute()
            == 0
        )

    def test_a_failing_tenant_is_audited_and_does_not_stop_the_others(self) -> None:
        broken, healthy = late_flow(), late_flow()
        broken.container.clock.set_speed(1.0)
        broken.container.clock.resume()
        healthy.container.clock.set_speed(1.0)
        healthy.container.clock.resume()

        def boom() -> list:  # type: ignore[type-arg]
            raise RuntimeError("fallo simulado")

        object.__setattr__(broken.ws.track, "execute", boom)
        audit = InMemoryAuditLog()
        catalog = Catalog(
            (tenant("rota"), SimpleNamespace(routing=broken.ws)),
            (tenant("sana"), SimpleNamespace(routing=healthy.ws)),
        )
        assert ScheduledTracking(catalog, audit, Clock()).execute() == 1
        by_action = {(e.action, e.tenant_id) for e in audit.list_events(None)}
        assert ("routing.tracking.scheduled", "t-rota") in by_action
        assert ("routing.proposal.auto", "t-sana") in by_action

    def test_each_tenant_only_touches_its_own_workspace(self) -> None:
        a, b = late_flow(), late_flow()
        for f in (a, b):
            f.container.clock.set_speed(1.0)
            f.container.clock.resume()
        catalog = Catalog(
            (tenant("a"), SimpleNamespace(routing=a.ws)),
            (tenant("b"), SimpleNamespace(routing=b.ws)),
        )
        ScheduledTracking(catalog, InMemoryAuditLog(), Clock()).execute()
        assert len(a.ws.core.repo.proposals()) == 1 and len(b.ws.core.repo.proposals()) == 1
        assert a.ws.core.repo is not b.ws.core.repo


class TestWorkspaceCatalog:
    def test_only_created_and_active_workspaces_are_listed(self) -> None:
        registry = InMemoryTenantRegistry()
        active, suspended = tenant("a"), tenant("b").suspended()
        registry.save(active)
        registry.save(suspended)
        provider = InMemoryTenantWorkspaceProvider(
            registry, lambda t: SimpleNamespace(tenant=t.slug)
        )  # type: ignore[arg-type,return-value]
        assert provider.active_workspaces() == []  # nada se crea por listar

        from fleetplanner.domain.tenancy.models import Principal, Role

        for slug, tid in (("a", active.id), ("b", suspended.id)):
            provider._cache[tid.value] = SimpleNamespace(tenant=slug)  # noqa: SLF001
        listed = provider.active_workspaces()
        assert [(t.slug, ws.tenant) for t, ws in listed] == [("a", "a")]
        assert Principal and Role  # las importaciones documentan el contexto de tenant
