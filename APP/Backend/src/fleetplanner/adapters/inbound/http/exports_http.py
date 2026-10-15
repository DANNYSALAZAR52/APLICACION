"""Arma las hojas de cálculo que se descargan (tablero de capacidad y hoja de ruta)."""

from __future__ import annotations

from fleetplanner.adapters.inbound.http.schemas import DashboardResponse
from fleetplanner.adapters.inbound.http.schemas_routing import DriverRouteOut
from fleetplanner.application.ports.outbound.exports import Sheet
from fleetplanner.domain.routing.time_window import format_clock

_STATE = {"completed": "Entregada", "in_service": "En servicio", "pending": "Pendiente"}


def dashboard_sheets(d: DashboardResponse) -> list[Sheet]:
    notes = (
        d.demo_label,
        f"Versión del algoritmo: {d.algorithm_version}",
        f"Calculado: {d.run_at}",
    )
    fleet = Sheet(
        "Flota por método",
        [
            "Tipo",
            "Flota actual",
            "Balance",
            "Lean",
            "Monte Carlo P95",
            "Mix óptimo",
            "Propio vs tercero",
            "Brecha",
        ],
        [
            [
                r.vehicle_type,
                r.current,
                r.balance,
                r.lean,
                r.monte_carlo_p95,
                r.mix,
                r.own_vs_third,
                r.gap,
            ]
            for r in [*d.fleet, d.totals]
        ],
        notes,
    )
    corridors = Sheet(
        "Corredores",
        [
            "Código",
            "Nombre",
            "Tipo",
            "Demanda de diseño (t)",
            "Media (t)",
            "Desv. (t)",
            "Días válidos",
            "Ciclo (h)",
            "Viajes/día",
            "Capacidad efectiva (t/día)",
        ],
        [
            [
                c.code,
                c.name,
                c.vehicle_type,
                c.design_t,
                c.mean_t,
                c.std_t,
                c.valid_days,
                c.cycle_h,
                c.trips_per_day,
                c.effective_t_per_day,
            ]
            for c in d.corridors
        ],
        notes,
    )
    projection = Sheet(
        "Proyección",
        ["Escenario", "Año", "Flota requerida total", "Déficit desde"],
        [
            [p.scenario, y.year, y.total_required, p.first_deficit_year]
            for p in d.projections
            for y in p.years
        ],
        notes,
    )
    k = d.kpis
    kpis = Sheet(
        "Indicadores",
        ["Indicador", "Valor"],
        [
            ["Utilización de la flota", k.fleet_utilization],
            ["OEE", k.oee],
            ["Llenado", k.fill_pct],
            ["Km vacíos", k.empty_km_pct],
            ["Costo diario", k.daily_cost],
            ["Costo por tonelada", k.cost_per_ton],
            ["Costo por tonelada-km", k.cost_per_ton_km],
        ],
        notes,
    )
    return [fleet, corridors, projection, kpis]


def driver_sheet(route: DriverRouteOut) -> Sheet:
    return Sheet(
        "Hoja de ruta",
        [
            "#",
            "Parada",
            "Dirección",
            "Ventana",
            "Llegada estimada",
            "Salida estimada",
            "Carga (kg)",
            "Estado",
        ],
        [
            [
                s.stop.sequence,
                s.stop.label,
                s.address,
                (
                    f"{format_clock(s.stop.window_start_min)}–{format_clock(s.stop.window_end_min)}"
                    if s.stop.window_start_min is not None and s.stop.window_end_min is not None
                    else ""
                ),
                format_clock(s.stop.arrival_min),
                format_clock(s.stop.departure_min),
                s.stop.kg,
                _STATE.get(s.stop.state, s.stop.state),
            ]
            for s in route.stops
        ],
        (route.demo_label, f"Vehículo: {route.plate}", f"Plan versión {route.plan_version}"),
    )
