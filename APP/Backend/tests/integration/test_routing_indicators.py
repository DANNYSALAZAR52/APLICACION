"""Escenarios de indicadores: plan estático vs. dinámico con los mismos pedidos y denominadores."""

from __future__ import annotations

import pytest

from fleetplanner.application.use_cases.routing.indicators import DEFINITIONS
from routing_flow_helpers import Flow, seeded


@pytest.fixture(scope="module")
def scenarios():  # type: ignore[no-untyped-def]
    flow = seeded(customers=14, vehicles=3, seed=5)
    return flow, {s.key: s for s in flow.ws.indicators.scenarios()}


class TestScenarios:
    def test_there_are_four_labelled_scenarios(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        assert list(by_key) == ["clean", "static_events", "dynamic_events", "dynamic_incomplete"]
        assert all(s.title and s.description for s in by_key.values())

    def test_without_events_the_morning_plan_is_fully_punctual(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        k = by_key["clean"].kpis
        assert k.punctuality == 1.0 and k.otif == 1.0
        assert k.committed_orders == 14 and by_key["clean"].events == ()

    def test_both_event_scenarios_use_the_same_events_orders_and_denominator(
        self, scenarios
    ) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        static, dynamic = by_key["static_events"], by_key["dynamic_events"]
        assert static.events == dynamic.events and len(static.events) >= 3
        assert static.kpis.committed_orders == dynamic.kpis.committed_orders == 15

    def test_static_plan_leaves_orders_unattended_and_dynamic_attends_them(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        static, dynamic = by_key["static_events"], by_key["dynamic_events"]
        assert static.kpis.unattended_orders >= 1
        assert dynamic.kpis.unattended_orders < static.kpis.unattended_orders
        assert dynamic.kpis.delivered_orders > static.kpis.delivered_orders
        assert dynamic.plan_versions > 1 and static.plan_versions == 1

    def test_dynamic_activates_a_reserve_only_when_it_is_used(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        assert by_key["static_events"].reserve_activations == 0
        assert by_key["clean"].reserve_activations == 0
        assert by_key["dynamic_events"].reserve_activations >= 1

    def test_incomplete_example_lowers_otif_without_changing_punctuality(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        base, example = by_key["dynamic_events"], by_key["dynamic_incomplete"]
        assert example.incomplete_rate == 0.10
        assert example.kpis.punctuality == base.kpis.punctuality
        assert example.kpis.otif < base.kpis.otif
        assert example.kpis.incomplete_orders >= 1

    def test_punctuality_and_otif_are_never_conflated(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        _, by_key = scenarios
        for s in by_key.values():
            k = s.kpis
            assert k.otif is not None and k.punctuality is not None
            assert k.otif <= k.punctuality
            assert k.on_time_orders + k.late_orders == k.delivered_orders

    def test_results_are_cached_and_reproducible(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        flow, by_key = scenarios
        again = {s.key: s for s in flow.ws.indicators.scenarios()}
        assert again == by_key
        fresh = seeded(customers=14, vehicles=3, seed=5)
        assert {s.key: s.kpis for s in fresh.ws.indicators.scenarios()} == {
            k: v.kpis for k, v in by_key.items()
        }

    def test_running_the_scenarios_does_not_touch_the_live_day(self, scenarios) -> None:  # type: ignore[no-untyped-def]
        flow, _ = scenarios
        assert flow.ws.core.repo.active_plan() is None  # el día en curso ni siquiera empezó
        assert flow.ws.core.repo.events() == []


class TestDefinitions:
    def test_definitions_state_both_metrics_separately_and_the_denominator(self) -> None:
        text = " ".join(DEFINITIONS)
        assert "Puntualidad =" in text and "OTIF =" in text
        assert "mismo siempre" in text and "sin atender" in text
        assert "simulaciones" in text


class TestLiveIndicators:
    def test_projection_updates_with_the_clock_and_the_plan(self) -> None:
        flow: Flow = seeded(customers=10, vehicles=2)
        flow.ws.day.start("t")
        flow.at(5)
        early = flow.ws.indicators.live(flow.ws)
        flow.at(11)
        later = flow.ws.indicators.live(flow.ws)
        assert early.delivered_so_far == 0 < later.delivered_so_far
        assert later.projected.committed_orders == 10
        assert later.on_time_so_far <= later.delivered_so_far
        assert later.plan_version == 1
