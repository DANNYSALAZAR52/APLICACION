"""Informe de texto del tablero de capacidad (CLI)."""

from __future__ import annotations

from fleetplanner.application.dto.capacity import CapacityDashboard
from fleetplanner.application.use_cases.build_capacity_dashboard import BuildCapacityDashboard


def _row(label: str, values: dict[str, int | str], types: list[str]) -> str:
    cells = "".join(f"{values.get(t, '-')!s:>14}" for t in types)
    return f"{label:<26}{cells}"


def render_dashboard(dashboard: CapacityDashboard, demo_label: str | None = None) -> str:
    """Texto legible del tablero. ``demo_label`` se imprime de forma destacada si se indica."""
    balance = dashboard.balance
    requirement = balance.requirement
    types = sorted(set(requirement.required_by_type) | set(requirement.current_by_type))
    lines: list[str] = []
    if demo_label:
        lines += [f"*** {demo_label} ***", ""]
    lines += [
        f"Tablero de capacidad de flota — corrida {dashboard.run_at.isoformat(timespec='seconds')}",
        f"Versión del algoritmo: {dashboard.algorithm_version} · año base {dashboard.base_year}",
        "",
        _row("", {t: t for t in types}, types) + f"{'TOTAL':>14}",
        _row("Flota actual", dict(requirement.current_by_type), types)
        + f"{requirement.total_current:>14}",
        _row("Balance (P3)", dict(requirement.required_by_type), types)
        + f"{requirement.total_required:>14}",
        _row("Lean (P5)", dict(dashboard.lean.required_by_type), types)
        + f"{dashboard.lean.total_required:>14}",
        _row(
            "Monte Carlo P95 (P6)",
            {t: p["p95"] for t, p in dashboard.monte_carlo.percentiles_by_type.items()},
            types,
        )
        + f"{dashboard.monte_carlo.p95_total:>14}",
        _row("Mix óptimo (P7)", dict(dashboard.mix.fleet_by_type), types)
        + f"{dashboard.mix.total_vehicles:>14}  [{dashboard.mix.status.value}]",
        _row(
            "Propio vs tercero (P8)",
            {t: r.optimal_own for t, r in dashboard.own_vs_third.by_type.items()},
            types,
        )
        + f"{dashboard.own_vs_third.total_own:>14}",
        _row("Brecha (actual − req.)", dict(requirement.gap_by_type), types)
        + f"{requirement.total_gap:>14}",
        "",
        "Proyección a 5 años (flota requerida total):",
    ]
    for projection in dashboard.projections:
        series = ", ".join(f"{y.year}: {y.requirement.total_required}" for y in projection.years)
        deficit = projection.first_deficit_year or "sin déficit en el horizonte"
        lines.append(f"  {projection.scenario:<10} {series}  · primer déficit: {deficit}")

    kpis = balance.kpis
    lines += [
        "",
        "KPI (sobre la flota del balance):",
        f"  Utilización de flota: {_pct(kpis.fleet_utilization)} · OEE: {_pct(kpis.oee)} · "
        f"llenado: {_pct(kpis.fill_pct)} · km en vacío: {_pct(kpis.empty_km_pct)}",
        f"  Costo diario: {kpis.daily_cost:,.0f} · por tonelada: {_money(kpis.cost_per_ton)} · "
        f"por t-km: {_money(kpis.cost_per_ton_km)} · OTIF: no disponible en esta fase",
        "",
        "Hallazgos:",
        *[f"  - {finding}" for finding in dashboard.findings],
    ]
    if dashboard.warnings:
        lines += ["", "Advertencias:", *[f"  ! {w}" for w in dashboard.warnings]]
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    return "n/d" if value is None else f"{value * 100:.1f} %"


def _money(value: float | None) -> str:
    return "n/d" if value is None else f"{value:,.1f}"


def run_capacity_cli(use_case: BuildCapacityDashboard, demo_label: str | None = None) -> str:
    """Ejecuta el caso de uso y devuelve el informe de texto."""
    return render_dashboard(use_case.execute(), demo_label)
