"""Modelos de ML con semilla fija sobre el fixture sintético (DOCS.MD §13.5).

Las comprobaciones son de comportamiento sobre ESTE fixture, no afirman rendimiento general.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fleetplanner.adapters.outbound.demo_data import history_reader_for_slug
from fleetplanner.adapters.outbound.demo_data.ml_history import (
    DemoHistoryReader,
    MlCorridor,
    MlCustomer,
)
from fleetplanner.adapters.outbound.ml import (
    SklearnAnomalyDetector,
    SklearnDelayRiskPredictor,
    SklearnDemandForecaster,
    SklearnPatternMiner,
)
from fleetplanner.adapters.outbound.ml import demand as demand_module
from fleetplanner.application.dto.ml import TrainedArtifact
from fleetplanner.domain.ml.calendar_co import is_holiday
from fleetplanner.domain.ml.records import OperationalHistory
from fleetplanner.domain.shared.errors import InsufficientDataError

A = "empresa-demo-a"
B = "empresa-demo-b"
SEED = 11


@pytest.fixture(scope="module")
def reader() -> DemoHistoryReader:
    return history_reader_for_slug(A)


@pytest.fixture(scope="module")
def history(reader: DemoHistoryReader) -> OperationalHistory:
    return reader.load()


@pytest.fixture(scope="module")
def demand(history: OperationalHistory) -> TrainedArtifact:
    return SklearnDemandForecaster().train(history, SEED)


@pytest.fixture(scope="module")
def anomalies(history: OperationalHistory) -> TrainedArtifact:
    return SklearnAnomalyDetector().train(history, SEED)


@pytest.fixture(scope="module")
def delay(history: OperationalHistory) -> TrainedArtifact:
    return SklearnDelayRiskPredictor().train(history, SEED)


@pytest.fixture(scope="module")
def segments(history: OperationalHistory) -> TrainedArtifact:
    return SklearnPatternMiner().train(history, SEED)


class TestSyntheticGenerator:
    def test_same_seed_gives_identical_history(self) -> None:
        first = history_reader_for_slug(A)._generate()  # noqa: SLF001
        second = history_reader_for_slug(A)._generate()  # noqa: SLF001
        assert first.visits == second.visits
        assert {c: s.observations for c, s in first.demand.items()} == {
            c: s.observations for c, s in second.demand.items()
        }

    def test_companies_have_different_data(self) -> None:
        a, b = history_reader_for_slug(A).load(), history_reader_for_slug(B).load()
        assert {v.customer_code for v in a.visits} != {v.customer_code for v in b.visits}
        assert a.provenance != b.provenance

    def test_history_is_declared_synthetic_and_lists_the_seeded_patterns(
        self, history: OperationalHistory
    ) -> None:
        assert "SINTÉTICOS" in history.provenance
        assert "esperas largas los viernes" in history.provenance
        assert 60 <= history.span_days <= 90

    def test_missing_days_are_absent_not_zero(self, history: OperationalHistory) -> None:
        for series in history.demand.values():
            assert all(value > 0 for value in series.observations.values())
            assert len(series.observations) < history.span_days

    def test_seeded_demand_patterns_exist_in_the_data(self, history: OperationalHistory) -> None:
        series = next(iter(history.demand.values())).observations
        mondays = [v for d, v in series.items() if d.weekday() == 0 and not is_holiday(d)]
        wednesdays = [v for d, v in series.items() if d.weekday() == 2 and not is_holiday(d)]
        assert sum(mondays) / len(mondays) > sum(wednesdays) / len(wednesdays)
        holidays = [v for d, v in series.items() if is_holiday(d) and d.weekday() < 6]
        normal = [v for d, v in series.items() if not is_holiday(d) and d.weekday() == 1]
        if holidays:
            assert sum(holidays) / len(holidays) < sum(normal) / len(normal)

    def test_needs_corridors_and_customers(self) -> None:
        with pytest.raises(ValueError, match="corredores y clientes"):
            DemoHistoryReader([], [], seed=1)


class TestDemandForecast:
    def test_model_beats_the_naive_seasonal_baseline_on_the_temporal_holdout(
        self, demand: TrainedArtifact
    ) -> None:
        m = demand.metrics
        assert m["mae"] < m["mae_baseline"]
        assert m["mape"] < m["mape_baseline"]
        assert m["n_test"] >= 20

    def test_p90_has_reasonable_coverage_on_the_holdout(self, demand: TrainedArtifact) -> None:
        # No es un umbral de negocio: el P90 debe cubrir claramente más que el P50 (~50 %).
        assert 0.6 <= demand.metrics["p90_coverage"] <= 1.0

    def test_forecasts_have_ordered_quantiles_and_the_requested_horizon(
        self, demand: TrainedArtifact, history: OperationalHistory
    ) -> None:
        last = history.last_day
        assert last is not None
        first_day = last + timedelta(days=1)
        forecasts = SklearnDemandForecaster().forecast(demand.payload, history, first_day, 7)
        assert len(forecasts) == 7 * len(history.demand)
        assert all(f.p90_t >= f.p50_t >= 0 for f in forecasts)
        assert {f.day for f in forecasts} == {first_day + timedelta(days=k) for k in range(7)}
        assert all(f.baseline_t is not None for f in forecasts)

    def test_weekday_pattern_is_learned(
        self, demand: TrainedArtifact, history: OperationalHistory
    ) -> None:
        # Domingo (poca demanda) frente a martes: el modelo aprendió el patrón semanal.
        forecasts = SklearnDemandForecaster().forecast(
            demand.payload, history, date(2026, 10, 10), 7
        )
        corridor = sorted(history.demand)[0]
        by_day = {f.day: f.p50_t for f in forecasts if f.corridor_code == corridor}
        assert by_day[date(2026, 10, 11)] < by_day[date(2026, 10, 13)]  # domingo < martes

    def test_features_use_only_the_past(self, history: OperationalHistory) -> None:
        code = sorted(history.demand)[0]
        obs = dict(history.demand[code].observations)
        target = max(obs)
        before = demand_module._features(target, obs, 10.0)  # noqa: SLF001
        # Alterar el propio día objetivo y "el futuro" no cambia sus variables.
        tampered = {**obs, target: obs[target] * 5, target + timedelta(days=1): 999.0}
        assert demand_module._features(target, tampered, 10.0) == before  # noqa: SLF001

    def test_importances_sum_to_one_or_zero(self, demand: TrainedArtifact) -> None:
        total = sum(demand.importances.values())
        assert total == pytest.approx(1.0) or total == 0.0

    def test_horizon_is_limited_to_seven_days(
        self, demand: TrainedArtifact, history: OperationalHistory
    ) -> None:
        with pytest.raises(InsufficientDataError):
            SklearnDemandForecaster().forecast(demand.payload, history, date(2026, 10, 10), 8)

    def test_too_little_history_is_refused(self) -> None:
        tiny = DemoHistoryReader(
            [MlCorridor("C", "C", 10.0)], [MlCustomer("K", "K", 480, 600)], seed=1, days=10
        ).load()
        with pytest.raises(InsufficientDataError):
            SklearnDemandForecaster().train(tiny, SEED)

    def test_training_is_reproducible(self, history: OperationalHistory) -> None:
        again = SklearnDemandForecaster().train(history, SEED)
        first = SklearnDemandForecaster().train(history, SEED)
        assert again.metrics == first.metrics
        last = history.last_day
        assert last is not None
        day = last + timedelta(days=1)
        assert SklearnDemandForecaster().forecast(
            again.payload, history, day, 3
        ) == SklearnDemandForecaster().forecast(first.payload, history, day, 3)


class TestAnomalies:
    def test_the_seeded_friday_wait_pattern_is_found_first(
        self,
        anomalies: TrainedArtifact,
        history: OperationalHistory,
        reader: DemoHistoryReader,
    ) -> None:
        found = SklearnAnomalyDetector().detect(anomalies.payload, history, 10)
        assert found
        top = found[0]
        assert top.customer_code == reader.seeded_customer
        assert top.kind == "espera"
        assert top.weekday == 4  # viernes
        assert (top.hour_from, top.hour_to) == (10, 12)
        assert top.ratio >= 2.0
        assert "los viernes entre las 10:00 y las 12:00" in top.message

    def test_results_are_sorted_by_severity(
        self, anomalies: TrainedArtifact, history: OperationalHistory
    ) -> None:
        found = SklearnAnomalyDetector().detect(anomalies.payload, history, 10)
        severities = [a.severity for a in found]
        assert severities == sorted(severities, reverse=True)

    def test_needs_enough_visits(self) -> None:
        empty = OperationalHistory(demand={}, visits=(), provenance="x")
        with pytest.raises(InsufficientDataError):
            SklearnAnomalyDetector().train(empty, SEED)


class TestDelayRisk:
    def test_classifier_beats_the_naive_base_rate(self, delay: TrainedArtifact) -> None:
        m = delay.metrics
        assert m["auc"] > 0.55  # mejor que el azar (0,5) en la partición temporal
        assert m["brier"] < m["brier_baseline"]  # mejor calibrado que la tasa base
        assert 0.0 < m["base_rate"] < 1.0

    def test_traffic_is_among_the_most_important_variables(self, delay: TrainedArtifact) -> None:
        ranked = sorted(delay.importances, key=lambda k: delay.importances[k], reverse=True)
        assert "factor de tráfico" in ranked[:3]

    def test_predictions_are_probabilities_sorted_by_risk(
        self, delay: TrainedArtifact, history: OperationalHistory
    ) -> None:
        risks = SklearnDelayRiskPredictor().predict(delay.payload, history, 10)
        assert len(risks) == 10
        assert all(0.0 <= r.probability <= 1.0 for r in risks)
        probabilities = [r.probability for r in risks]
        assert probabilities == sorted(probabilities, reverse=True)

    def test_higher_traffic_means_higher_risk_on_average(self, history: OperationalHistory) -> None:
        light = [v for v in history.visits if v.traffic_factor < 1.2]
        heavy = [v for v in history.visits if v.traffic_factor >= 1.4]
        assert sum(v.late for v in heavy) / len(heavy) > sum(v.late for v in light) / len(light)


class TestSegments:
    def test_every_customer_is_in_exactly_one_segment(
        self, segments: TrainedArtifact, history: OperationalHistory
    ) -> None:
        result = SklearnPatternMiner().segments(segments.payload, history)
        assert 2 <= len(result) <= 4
        members = [c for s in result for c in s.customers]
        assert sorted(members) == sorted({v.customer_code for v in history.visits})
        assert len(members) == len(set(members))
        assert len({s.name for s in result}) == len(result)
        assert all(s.description for s in result)

    def test_too_few_customers_are_refused(self) -> None:
        small = DemoHistoryReader(
            [MlCorridor("C", "C", 10.0)],
            [MlCustomer(f"K{i}", f"K{i}", 480, 600) for i in range(4)],
            seed=2,
            days=70,
        ).load()
        with pytest.raises(InsufficientDataError):
            SklearnPatternMiner().train(small, SEED)


class TestTenantSeparation:
    def test_a_model_trained_for_one_company_only_knows_its_own_corridors_and_customers(
        self,
    ) -> None:
        import pickle  # noqa: S403 - solo para inspeccionar el artefacto propio en la prueba

        a = history_reader_for_slug(A).load()
        b = history_reader_for_slug(B).load()
        # Las dos empresas comparten códigos de cliente (C-001...), por lo que la separación
        # se prueba con los datos: cada artefacto contiene SOLO el nivel de sus corredores y
        # los clientes de su propio historial.
        art_a = SklearnDemandForecaster().train(a, SEED)
        levels_a = pickle.loads(art_a.payload)["levels"]  # noqa: S301  # nosec B301
        assert set(levels_a) == set(a.demand)
        delay_b = SklearnDelayRiskPredictor().train(b, SEED)
        index_b = pickle.loads(delay_b.payload)["index"]  # noqa: S301  # nosec B301
        assert set(index_b) == {v.customer_code for v in b.visits}
        assert len(index_b) == 22 and len({v.customer_code for v in a.visits}) == 36
