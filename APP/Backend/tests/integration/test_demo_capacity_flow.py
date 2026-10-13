"""Flujo de capacidad de punta a punta con los adaptadores reales de la demo (sin red ni Docker).

No es una prueba contra PostgreSQL: la persistencia es en memoria (DEMO-ONLY).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fleetplanner.adapters.inbound.cli import render_dashboard
from fleetplanner.adapters.outbound.clock import FixedClock
from fleetplanner.bootstrap.container import build_capacity_container
from fleetplanner.domain.capacity.fleet_mix import SolverStatus
from fleetplanner.domain.capacity.results import CapacityMethod

NOW = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)


def _run():  # type: ignore[no-untyped-def]
    container = build_capacity_container(clock=FixedClock(NOW))
    return container, container.dashboard.execute()


def test_full_flow_produces_every_method_with_real_solver() -> None:
    container, dashboard = _run()
    assert dashboard.mix.status is SolverStatus.OPTIMAL
    assert dashboard.balance.requirement.total_required > 0
    assert dashboard.lean.total_required <= dashboard.balance.requirement.total_required
    assert {p.scenario for p in dashboard.projections} == {"base", "optimista", "pesimista"}
    assert {r.method for r in container.results.list_all()} == set(CapacityMethod)


def test_demo_run_is_reproducible() -> None:
    _, first = _run()
    _, second = _run()
    assert first.balance.requirement.required_by_type == second.balance.requirement.required_by_type
    assert first.monte_carlo == second.monte_carlo
    assert first.mix.fleet_by_type == second.mix.fleet_by_type


def test_report_labels_demo_data_and_declares_otif_unavailable() -> None:
    _, dashboard = _run()
    text = render_dashboard(dashboard, demo_label="DATOS DE DEMOSTRACIÓN")
    assert text.startswith("*** DATOS DE DEMOSTRACIÓN ***")
    assert "OTIF: no disponible" in text
    assert "Pronóstico de demanda con ML no disponible" in text


def test_own_vs_third_found_a_split_for_the_demo_dataset() -> None:
    _, dashboard = _run()
    assert dashboard.own_vs_third.by_type, "el dataset de demo debe tener días completos"
    assert dashboard.own_vs_third.total_own > 0
