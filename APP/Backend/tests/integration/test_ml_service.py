"""Servicio de ML por empresa: entrenamiento, versiones, integridad, reentrenamiento y tablero."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fleetplanner.adapters.outbound.clock import BOGOTA_TZ, FixedClock
from fleetplanner.adapters.outbound.ml import (
    SklearnAnomalyDetector,
    SklearnDelayRiskPredictor,
    SklearnDemandForecaster,
    SklearnPatternMiner,
)
from fleetplanner.adapters.outbound.persistence_memory import InMemoryModelRegistry
from fleetplanner.application.dto.ml import MODEL_NAMES, TrainedArtifact
from fleetplanner.application.use_cases.ml.service import MIN_HISTORY_DAYS, MlService
from fleetplanner.bootstrap.container import build_capacity_container
from fleetplanner.domain.shared.errors import ArtifactIntegrityError, InsufficientDataError
from tenancy_helpers import A, B, _small_history_reader

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=BOGOTA_TZ)


def make_service(slug: str = A, clock: FixedClock | None = None) -> tuple[MlService, FixedClock]:
    clock = clock or FixedClock(NOW)
    service = MlService(
        _small_history_reader(slug),
        SklearnDemandForecaster(),
        SklearnAnomalyDetector(),
        SklearnDelayRiskPredictor(),
        SklearnPatternMiner(),
        InMemoryModelRegistry(),
        clock,
    )
    return service, clock


@pytest.fixture(scope="module")
def trained_a() -> MlService:
    service, _ = make_service(A)
    service.report()
    return service


class TestRegistry:
    def test_versions_increase_and_hash_matches_the_artifact(self) -> None:
        registry = InMemoryModelRegistry()
        artifact = TrainedArtifact(b"abc", {"x": 1.0}, dataset_description="d", library="lib")
        first = registry.register("m", artifact, NOW, 7)
        second = registry.register("m", artifact, NOW, 7)
        assert (first.version, second.version) == (1, 2)
        assert first.artifact_sha256 == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
        assert registry.latest("m") == second
        assert [m.version for m in registry.versions("m")] == [1, 2]

    def test_a_tampered_artifact_is_never_loaded(self) -> None:
        registry = InMemoryModelRegistry()
        registry.register("m", TrainedArtifact(b"original", {}), NOW, 1)
        registry._records["m"][-1].payload = b"malicious"  # noqa: SLF001
        with pytest.raises(ArtifactIntegrityError, match="no coincide"):
            registry.load("m")

    def test_unknown_model_is_an_error_not_an_empty_artifact(self) -> None:
        with pytest.raises(ArtifactIntegrityError):
            InMemoryModelRegistry().load("nope")

    def test_registries_do_not_share_state(self) -> None:
        one, other = InMemoryModelRegistry(), InMemoryModelRegistry()
        one.register("m", TrainedArtifact(b"x", {}), NOW, 1)
        assert other.latest("m") is None


class TestTraining:
    def test_report_trains_on_first_use_with_visible_provenance(self, trained_a: MlService) -> None:
        report = trained_a.report()
        assert report.status == "ok"
        assert report.demo_label == "DATOS DE DEMOSTRACIÓN"
        assert "SINTÉTICOS" in report.provenance
        assert [m.metadata.name for m in report.models] == list(MODEL_NAMES)
        for card in report.models:
            assert card.metadata.version == 1
            assert len(card.metadata.artifact_sha256) == 64
            assert card.metadata.library.startswith("scikit-learn")
            assert card.metric_lines
        assert any("SINTÉTICOS" in limit for limit in report.limits)

    def test_forecast_comparison_is_per_corridor_for_the_next_day(
        self, trained_a: MlService
    ) -> None:
        comparison = trained_a.forecast_comparison()
        assert {c.corridor_code for c in comparison} == {"C1", "C2", "C3"}
        assert len({c.day for c in comparison}) == 1
        assert all(c.p90_t >= c.p50_t for c in comparison)
        assert all(c.historical_p90_t is not None for c in comparison)

    def test_the_report_is_cached_until_retrained(self) -> None:
        service, _ = make_service()
        first = service.report()
        assert service.report() is first
        service.train()
        second = service.report()
        assert second is not first
        assert {m.metadata.version for m in second.models} == {2}

    def test_each_company_gets_its_own_models_and_data(self) -> None:
        a, _ = make_service(A)
        b, _ = make_service(B)
        report_a, report_b = a.report(), b.report()
        customers_a = {c for s in report_a.segments for c in s.customers}
        customers_b = {c for s in report_b.segments for c in s.customers}
        assert len(customers_a) == 12 and len(customers_b) == 10
        assert report_a.provenance != report_b.provenance
        assert {m.metadata.artifact_sha256 for m in report_a.models}.isdisjoint(
            {m.metadata.artifact_sha256 for m in report_b.models}
        )

    def test_not_enough_history_is_explained(self) -> None:
        from fleetplanner.adapters.outbound.demo_data.ml_history import (
            DemoHistoryReader,
            MlCorridor,
            MlCustomer,
        )

        short = DemoHistoryReader(
            [MlCorridor("C", "C", 5.0)], [MlCustomer("K", "K", 480, 600)], seed=1, days=10
        )
        service = MlService(
            short,
            SklearnDemandForecaster(),
            SklearnAnomalyDetector(),
            SklearnDelayRiskPredictor(),
            SklearnPatternMiner(),
            InMemoryModelRegistry(),
            FixedClock(NOW),
        )
        with pytest.raises(InsufficientDataError, match=str(MIN_HISTORY_DAYS)):
            service.report()

    def test_a_corrupted_artifact_blocks_the_report(self) -> None:
        service, _ = make_service()
        service.report()
        registry = service._registry  # noqa: SLF001
        registry._records[MODEL_NAMES[1]][-1].payload = b"x"  # noqa: SLF001
        service._report = None  # noqa: SLF001
        with pytest.raises(ArtifactIntegrityError):
            service.report()


class TestScheduledRetraining:
    def test_never_trains_cold(self) -> None:
        service, _ = make_service()
        assert service.retrain_if_due() is False
        assert not service.is_trained()

    def test_retrains_only_after_the_interval(self) -> None:
        service, clock = make_service()
        service.report()
        assert service.retrain_if_due() is False
        clock.advance(timedelta(hours=23))
        assert service.retrain_if_due() is False
        clock.advance(timedelta(hours=2))
        assert service.retrain_if_due() is True
        assert {m.version for m in service.train()} == {3}  # v1 inicial, v2 programado, v3 manual


class TestCapacityDashboardIntegration:
    def test_dashboard_carries_the_ml_forecast_and_drops_the_unavailable_warning(self) -> None:
        service, clock = make_service()
        dashboard = build_capacity_container(clock=clock, ml=service).dashboard.execute()
        assert dashboard.ml_forecast_available is True
        assert dashboard.ml_forecast
        assert not any("ML no disponible" in w for w in dashboard.warnings)

    def test_without_ml_the_dashboard_says_so(self) -> None:
        dashboard = build_capacity_container(clock=FixedClock(NOW)).dashboard.execute()
        assert dashboard.ml_forecast_available is False
        assert dashboard.ml_forecast == []
        assert any("ML no disponible" in w for w in dashboard.warnings)

    def test_a_failure_of_the_models_degrades_to_the_percentile_with_a_warning(self) -> None:
        class Broken:
            def forecast_comparison(self):  # type: ignore[no-untyped-def]
                raise InsufficientDataError("faltan datos")

        dashboard = build_capacity_container(clock=FixedClock(NOW), ml=Broken()).dashboard.execute()
        assert dashboard.ml_forecast_available is False
        assert any("faltan datos" in w for w in dashboard.warnings)
        assert dashboard.balance is not None  # el resto del tablero sigue funcionando
