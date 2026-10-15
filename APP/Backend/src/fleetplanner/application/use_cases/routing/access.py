"""Casos de uso de ruteo expuestos a los adaptadores de entrada: autorizan y auditan.

El tenant sale siempre de la `Principal`; ninguna operación recibe un identificador de empresa.
Los eventos y decisiones quedan en la auditoría con quién, qué y cuándo.
"""

from __future__ import annotations

from fleetplanner.application.dto.routing import (
    ConfirmationResult,
    DecisionResult,
    DriverRouteView,
    EventCommand,
    HandleEventResult,
    IndicatorsView,
    OperationsSnapshot,
    PlanDetail,
    ReportView,
    SimControl,
)
from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.tenancy import (
    AuditLogPort,
    RateLimiterPort,
    TenantWorkspaceProvider,
)
from fleetplanner.application.use_cases.routing.indicators import DEFINITIONS
from fleetplanner.application.use_cases.routing.snapshot import summarize
from fleetplanner.application.use_cases.routing.workspace import RoutingWorkspace
from fleetplanner.domain.routing.delivery import IncidentKind
from fleetplanner.domain.shared.errors import (
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
)
from fleetplanner.domain.tenancy.access_policy import AccessPolicy, Permission
from fleetplanner.domain.tenancy.models import Principal

SYSTEM_START_ACTOR = "sistema (05:00)"


class _RoutingAccess:
    def __init__(
        self,
        workspaces: TenantWorkspaceProvider,
        audit: AuditLogPort,
        clock: ClockPort,
        limiter: RateLimiterPort | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._audit = audit
        self._clock = clock
        self._limiter = limiter

    def _throttle(self, principal: Principal, bucket: str, limit: int) -> None:
        """Límite por usuario y empresa en operaciones que mutan o son costosas."""
        if self._limiter is None:
            return
        key = f"routing:{bucket}:{principal.tenant_id}:{principal.user_id}"
        if not self._limiter.allow(key, limit, 60):
            self.record(
                principal, f"routing.{bucket}", AuditOutcome.DENIED, detail={"motivo": "límite"}
            )
            raise RateLimitedError("Demasiadas operaciones seguidas; espere un momento.")

    def _routing(
        self, principal: Principal, permission: Permission, action: str
    ) -> RoutingWorkspace:
        if not AccessPolicy.can(principal, permission):
            self.record(principal, action, AuditOutcome.DENIED)
            raise PermissionDeniedError("No tiene permiso para esta operación de ruteo.")
        # El espacio de trabajo se resuelve por la identidad autenticada, nunca por un parámetro.
        return self._workspaces.workspace_for(principal).routing

    @staticmethod
    def _ensure_started(routing: RoutingWorkspace) -> None:
        if routing.core.repo.active_plan() is None:
            routing.day.start(SYSTEM_START_ACTOR)

    def record(
        self,
        principal: Principal,
        action: str,
        outcome: AuditOutcome,
        resource: str = "routing",
        detail: dict[str, str] | None = None,
    ) -> None:
        self._audit.record(
            AuditEvent(
                at=self._clock.now(),
                action=action,
                outcome=outcome,
                tenant_id=str(principal.tenant_id) if principal.tenant_id else None,
                actor_user_id=principal.user_id,
                actor_username=principal.username,
                resource=resource,
                detail=detail or {},
            )
        )


class GetControlTower(_RoutingAccess):
    def execute(self, principal: Principal) -> OperationsSnapshot:
        routing = self._routing(principal, Permission.ROUTING_READ, "routing.tower.view")
        with routing.lock:
            self._ensure_started(routing)
            return routing.snapshot.execute()


class RunTracking(_RoutingAccess):
    """Seguimiento periódico: recalcula horarios y propone re-secuenciar si hay retraso."""

    def execute(self, principal: Principal) -> OperationsSnapshot:
        routing = self._routing(principal, Permission.ROUTING_EVENTS, "routing.tracking.run")
        with routing.lock:
            self._ensure_started(routing)
            for proposal in routing.track.execute():
                self.record(
                    principal,
                    "routing.proposal.auto",
                    AuditOutcome.SUCCESS,
                    f"routing/proposals/{proposal.id}",
                    {"reason": proposal.reason},
                )
            return routing.snapshot.execute()


class InjectEvent(_RoutingAccess):
    def execute(self, principal: Principal, command: EventCommand) -> HandleEventResult:
        routing = self._routing(principal, Permission.ROUTING_EVENTS, "routing.event.inject")
        self._throttle(principal, "event", 30)
        with routing.lock:
            self._ensure_started(routing)
            result = routing.handle_event.execute(principal.username, command)
            self.record(
                principal,
                "routing.event.inject",
                AuditOutcome.SUCCESS,
                f"routing/events/{result.event.id}",
                {
                    "type": result.event.type.value,
                    "proposal": result.proposal.id,
                    "proposal_status": result.proposal.status.value,
                },
            )
            return result


class DecideProposal(_RoutingAccess):
    def execute(
        self, principal: Principal, proposal_id: str, approve: bool, comment: str = ""
    ) -> DecisionResult:
        routing = self._routing(principal, Permission.ROUTING_EVENTS, "routing.proposal.decide")
        with routing.lock:
            result = routing.approve.execute(principal.username, proposal_id, approve, comment)
            self.record(
                principal,
                "routing.proposal.approve" if approve else "routing.proposal.reject",
                AuditOutcome.SUCCESS,
                f"routing/proposals/{proposal_id}",
                {
                    "status": result.proposal.status.value,
                    "version": str(result.plan.version) if result.plan else "",
                },
            )
            return result


class ControlSimulation(_RoutingAccess):
    def execute(self, principal: Principal, command: SimControl) -> OperationsSnapshot:
        routing = self._routing(principal, Permission.ROUTING_EVENTS, "routing.sim.control")
        with routing.lock:
            self._ensure_started(routing)
            routing.day.control(command)
            self.record(
                principal,
                "routing.sim.control",
                AuditOutcome.SUCCESS,
                "routing/simulation",
                {"action": command.action.value, "value": str(command.value)},
            )
            return routing.snapshot.execute()


class ResetOperatingDay(_RoutingAccess):
    def execute(self, principal: Principal) -> OperationsSnapshot:
        routing = self._routing(principal, Permission.ROUTING_EVENTS, "routing.day.reset")
        self._throttle(principal, "reset", 6)
        with routing.lock:
            routing.day.start(principal.username)
            self.record(principal, "routing.day.reset", AuditOutcome.SUCCESS, "routing/day")
            return routing.snapshot.execute()


class GetPlanVersion(_RoutingAccess):
    def execute(self, principal: Principal, version: int) -> PlanDetail:
        routing = self._routing(principal, Permission.ROUTING_READ, "routing.plan.view")
        with routing.lock:
            self._ensure_started(routing)
            plans = routing.core.repo.plans()
            if not 1 <= version <= len(plans):
                raise NotFoundError("Esa versión del plan no existe.")
            plan = plans[version - 1]
            return PlanDetail(plan, summarize(plan))


class GetIndicators(_RoutingAccess):
    """Indicadores diarios: en vivo y comparación estático vs. dinámico (Gerencia y despacho)."""

    def execute(self, principal: Principal) -> IndicatorsView:
        routing = self._routing(principal, Permission.INDICATORS_READ, "routing.indicators.view")
        service = routing.indicators
        if service is None:  # pragma: no cover - el ensamblado siempre lo asigna
            raise NotFoundError("Los indicadores no están disponibles.")
        with routing.lock:
            self._ensure_started(routing)
            live = service.live(routing)
        # Los escenarios corren en un espacio aparte: no bloquean el día en curso de la empresa.
        scenarios = service.scenarios()
        return IndicatorsView(live=live, scenarios=scenarios, definitions=DEFINITIONS)


class _DriverAccess(_RoutingAccess):
    def _driver(self, principal: Principal, action: str) -> tuple[RoutingWorkspace, str]:
        routing = self._routing(principal, Permission.DRIVER_ROUTE, action)
        # El vehículo sale del usuario guardado, nunca de la solicitud.
        if not principal.vehicle_id:
            self.record(principal, action, AuditOutcome.DENIED, detail={"motivo": "sin vehículo"})
            raise PermissionDeniedError("Su usuario no tiene un vehículo asignado.")
        return routing, principal.vehicle_id


class GetDriverRoute(_DriverAccess):
    def execute(self, principal: Principal) -> DriverRouteView:
        routing, vehicle_id = self._driver(principal, "routing.driver.view")
        with routing.lock:
            self._ensure_started(routing)
            return routing.driver.route(vehicle_id)


class ConfirmDelivery(_DriverAccess):
    def execute(self, principal: Principal, order_id: str) -> ConfirmationResult:
        routing, vehicle_id = self._driver(principal, "routing.delivery.confirm")
        with routing.lock:
            self._ensure_started(routing)
            result = routing.driver.confirm(vehicle_id, principal.username, order_id)
            self.record(
                principal,
                "routing.delivery.confirm",
                AuditOutcome.SUCCESS,
                f"routing/orders/{order_id}",
                {"vehicle": vehicle_id, "ya_confirmada": str(result.already_confirmed)},
            )
            return result


class ReportIncident(_DriverAccess):
    def execute(
        self, principal: Principal, kind: IncidentKind, detail: str, order_id: str | None
    ) -> ReportView:
        routing, vehicle_id = self._driver(principal, "routing.driver.report")
        self._throttle(principal, "report", 20)
        with routing.lock:
            self._ensure_started(routing)
            report = routing.driver.report(vehicle_id, principal.username, kind, detail, order_id)
            self.record(
                principal,
                "routing.driver.report",
                AuditOutcome.SUCCESS,
                f"routing/reports/{report.id}",
                {"vehicle": vehicle_id, "tipo": kind.value},
            )
            return report
