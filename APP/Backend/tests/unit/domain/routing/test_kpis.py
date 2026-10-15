"""Indicadores diarios: puntualidad y OTIF son métricas distintas con el mismo denominador."""

from __future__ import annotations

import pytest

from fleetplanner.domain.routing.evaluation import evaluate_route
from fleetplanner.domain.routing.kpis import compute_kpis, incomplete_every
from routing_builders import DEPOT_POINT, PARAMS, constant_travel, spec


def timings(*windows: tuple[float, float], kg: float = 10.0):  # type: ignore[no-untyped-def]
    """Viaje de 10 min por tramo y servicio de 5 min: llegadas a 370, 385, 400..."""
    specs = [spec(f"P{i:02d}", s, e, kg=kg) for i, (s, e) in enumerate(windows, start=1)]
    load = kg * len(specs)
    return evaluate_route(
        DEPOT_POINT, 360, load, specs, DEPOT_POINT, 4050, PARAMS, constant_travel()
    ).timings


class TestPunctualityAndOtif:
    def test_everything_on_time_and_complete_is_100_percent_in_both(self) -> None:
        k = compute_kpis(timings((0, 500), (0, 500), (0, 500)), ["P01", "P02", "P03"])
        assert (k.punctuality, k.otif) == (1.0, 1.0)
        assert k.late_orders == 0 and k.unattended_orders == 0

    def test_arriving_exactly_at_the_end_of_the_window_is_on_time(self) -> None:
        # primera llegada a las 370; la ventana termina a las 370
        k = compute_kpis(timings((0, 370)), ["P01"])
        assert k.on_time_orders == 1 and k.late_orders == 0

    def test_one_minute_late_is_not_on_time(self) -> None:
        k = compute_kpis(timings((0, 369)), ["P01"])
        assert k.on_time_orders == 0 and k.late_orders == 1
        assert k.total_delay_min == pytest.approx(1.0)

    def test_unattended_orders_stay_in_the_denominator_as_not_fulfilled(self) -> None:
        # 3 comprometidos, solo 2 entregados a tiempo: 67 % (no 100 % de los entregados)
        k = compute_kpis(timings((0, 500), (0, 500)), ["P01", "P02", "P03"])
        assert k.unattended_orders == 1
        assert k.punctuality == pytest.approx(2 / 3)
        assert k.otif == pytest.approx(2 / 3)

    def test_incomplete_deliveries_lower_otif_but_not_punctuality(self) -> None:
        ten = [(0.0, 1400.0)] * 10
        k = compute_kpis(timings(*ten), [f"P{i:02d}" for i in range(1, 11)], incomplete_rate=0.10)
        assert k.punctuality == 1.0
        assert k.incomplete_orders == 1
        assert k.otif == pytest.approx(0.9)
        assert k.otif < k.punctuality  # no son la misma métrica

    def test_late_and_incomplete_orders_are_not_double_penalised(self) -> None:
        # con 2 pedidos y tasa 50 %: el 2.º queda incompleto; el 1.º llega tarde
        k = compute_kpis(timings((0, 369), (0, 1400)), ["P01", "P02"], incomplete_rate=0.5)
        assert k.on_time_orders == 1 and k.otif_orders == 0

    def test_incomplete_marking_is_deterministic(self) -> None:
        ids = [f"P{i:02d}" for i in range(1, 21)]
        windows = [(0.0, 1400.0)] * 20
        a = compute_kpis(timings(*windows), ids, 0.25)
        b = compute_kpis(timings(*windows), ids, 0.25)
        assert a == b and a.incomplete_orders == 5

    def test_no_committed_orders_gives_no_percentage(self) -> None:
        k = compute_kpis([], [])
        assert k.punctuality is None and k.otif is None

    def test_only_deliveries_count(self) -> None:
        from dataclasses import replace

        from fleetplanner.domain.routing.evaluation import StopKind

        base = timings((0, 500))
        reload_stop = replace(
            base[0], spec=replace(base[0].spec, kind=StopKind.RELOAD, order_id=None)
        )
        k = compute_kpis([*base, reload_stop], ["P01"])
        assert k.delivered_orders == 1


@pytest.mark.parametrize(
    ("rate", "every"), [(0.10, 10), (0.25, 4), (1.0, 1), (0.0, None), (-1, None)]
)
def test_incomplete_period(rate: float, every: int | None) -> None:
    assert incomplete_every(rate) == every
