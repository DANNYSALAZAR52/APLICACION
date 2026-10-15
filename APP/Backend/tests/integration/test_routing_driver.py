"""Hoja de ruta del conductor: su ruta, confirmar entregas y reportar novedades."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from fleetplanner.application.dto.routing import BreakdownCommand
from fleetplanner.domain.routing.delivery import IncidentKind
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError
from routing_builders import point
from routing_flow_helpers import Flow, cust, custom, seeded


def day(customers: int = 10) -> Flow:
    flow = seeded(customers=customers, vehicles=2)
    flow.ws.day.start("t")
    return flow


class TestDriverRoute:
    def test_lists_only_the_drivers_stops_in_order_with_addresses(self) -> None:
        flow = day()
        route = flow.ws.driver.route("V-01")
        assert route.plate == "T-01" and route.vehicle_id == "V-01"
        assert [d.stop.sequence for d in route.stops] == list(range(1, len(route.stops) + 1))
        assert {d.stop.vehicle_id for d in route.stops} == {"V-01"}
        assert all(d.address for d in route.stops)
        assert route.next_key == route.stops[0].stop.key

    def test_other_vehicles_stops_never_appear(self) -> None:
        flow = day()
        mine = {d.stop.order_id for d in flow.ws.driver.route("V-01").stops}
        theirs = {d.stop.order_id for d in flow.ws.driver.route("V-02").stops}
        assert mine and theirs and not (mine & theirs)

    def test_navigation_links_use_the_official_format_and_cover_the_pending_stops(self) -> None:
        flow = day(customers=25)
        route = flow.ws.driver.route("V-01")
        assert route.nav_links, "debe haber al menos un enlace"
        for link in route.nav_links:
            parts = urlparse(link.url)
            assert (parts.netloc, parts.path) == ("www.google.com", "/maps/dir/")
            query = parse_qs(parts.query)
            assert query["api"] == ["1"] and "key" not in query
            waypoints = query.get("waypoints", [""])[0]
            assert len(waypoints.split("|") if waypoints else []) <= 9
        assert sum(link.stops for link in route.nav_links) == len(route.stops)

    def test_a_long_route_is_split_into_chained_links(self) -> None:
        customers = [
            cust(f"C-{i:02d}", point(i).lat, point(i).lon, 7 * 60, 16 * 60) for i in range(1, 26)
        ]
        flow = custom(customers, [50.0] * 25, vehicles=1)
        flow.ws.day.start("t")
        route = flow.ws.driver.route("V-01")
        assert len(route.stops) == 25 and len(route.nav_links) == 3
        assert [link.stops for link in route.nav_links] == [10, 10, 5]
        assert "Tramo 1 de 3" in route.nav_links[0].label
        second = parse_qs(urlparse(route.nav_links[1].url).query)
        assert "origin" in second  # arranca donde terminó el tramo anterior

    def test_completed_stops_leave_the_navigation_links(self) -> None:
        flow = day()
        before = sum(link.stops for link in flow.ws.driver.route("V-01").nav_links)
        flow.at(13)
        later = flow.ws.driver.route("V-01")
        assert sum(link.stops for link in later.nav_links) < before
        done = [d for d in later.stops if d.stop.state == "completed"]
        assert done and later.next_key not in {d.stop.key for d in done}

    def test_a_reserve_without_route_is_told_to_wait(self) -> None:
        flow = day()
        route = flow.ws.driver.route("V-03")
        assert route.stops == () and route.nav_links == ()
        assert any("No tiene ruta" in n for n in route.notices)

    def test_a_vehicle_that_does_not_exist_has_no_route(self) -> None:
        with pytest.raises(NotFoundError):
            day().ws.driver.route("V-99")

    def test_after_a_reroute_the_driver_is_told_the_plan_changed(self) -> None:
        flow = day()
        flow.at(8)
        proposal = flow.ws.handle_event.execute("d", BreakdownCommand("V-02")).proposal
        flow.ws.approve.execute("d", proposal.id, True)
        route = flow.ws.driver.route("V-01")
        assert route.plan_version == 2
        assert any("plan versión 2" in n for n in route.notices)

    def test_a_broken_vehicle_gets_wait_instructions(self) -> None:
        flow = day()
        flow.at(8)
        proposal = flow.ws.handle_event.execute("d", BreakdownCommand("V-01")).proposal
        flow.ws.approve.execute("d", proposal.id, True)
        route = flow.ws.driver.route("V-01")
        assert route.route_status == "broken" and route.return_min is None
        assert any("averiado" in n for n in route.notices)

    def test_the_replacement_vehicle_is_told_to_go_to_the_transfer_point_first(self) -> None:
        flow = day()
        flow.at(8)
        proposal = flow.ws.handle_event.execute("d", BreakdownCommand("V-01")).proposal
        flow.ws.approve.execute("d", proposal.id, True)
        reserve = flow.ws.driver.route("V-03")
        assert any("punto de transbordo" in n for n in reserve.notices)
        assert reserve.stops[0].stop.kind == "transfer"
        assert "Punto de avería" in reserve.stops[0].address


class TestConfirmDelivery:
    def first_order(self, flow: Flow) -> str:
        return flow.ws.driver.route("V-01").stops[0].stop.order_id or ""

    def test_cannot_confirm_before_arriving_at_the_stop(self) -> None:
        flow = day()
        with pytest.raises(ConflictError, match="Aún no llega"):
            flow.ws.driver.confirm("V-01", "conductor", self.first_order(flow))

    def test_confirms_after_arriving_and_records_who_and_when(self) -> None:
        flow = day()
        order = self.first_order(flow)
        flow.at(9)
        result = flow.ws.driver.confirm("V-01", "conductor", order)
        assert (result.source, result.already_confirmed) == ("driver", False)
        stored = flow.ws.core.repo.confirmations()[order]
        assert stored.by == "conductor" and stored.minute == 540
        stop = next(s for s in flow.ws.snapshot.execute().stops if s.order_id == order)
        assert stop.confirmed_by == "driver" and stop.confirmed_min == 540

    def test_confirming_twice_is_idempotent(self) -> None:
        flow = day()
        order = self.first_order(flow)
        flow.at(9)
        flow.ws.driver.confirm("V-01", "conductor", order)
        again = flow.ws.driver.confirm("V-01", "conductor", order)
        assert again.already_confirmed and len(flow.ws.core.repo.confirmations()) == 1

    def test_a_geofence_confirmation_is_not_overwritten_by_the_driver(self) -> None:
        flow = day()
        order = self.first_order(flow)
        flow.ws.snapshot.execute()
        flow.at(11)
        flow.ws.snapshot.execute()  # la geocerca confirma sola
        result = flow.ws.driver.confirm("V-01", "conductor", order)
        assert result.already_confirmed and result.source == "geofence"

    def test_cannot_confirm_an_order_of_another_vehicle(self) -> None:
        flow = day()
        other = flow.ws.driver.route("V-02").stops[0].stop.order_id or ""
        flow.at(11)
        with pytest.raises(NotFoundError, match="no está en su ruta"):
            flow.ws.driver.confirm("V-01", "conductor", other)
        assert other not in flow.ws.core.repo.confirmations()

    def test_unknown_order_is_not_found(self) -> None:
        flow = day()
        flow.at(11)
        with pytest.raises(NotFoundError):
            flow.ws.driver.confirm("V-01", "conductor", "P-999")


class TestReportIncident:
    def test_the_report_reaches_the_dispatcher_as_an_alert_without_changing_the_plan(self) -> None:
        flow = day()
        order = flow.ws.driver.route("V-01").stops[0].stop.order_id
        report = flow.ws.driver.report(
            "V-01", "conductor", IncidentKind.CUSTOMER_ABSENT, "  Nadie  abre\n la puerta ", order
        )
        assert report.detail == "Nadie abre la puerta" and report.plate == "T-01"
        snap = flow.ws.snapshot.execute()
        assert snap.reports[0].id == report.id
        alert = next(a for a in snap.alerts if a.code == "driver_report")
        assert alert.level == "warning" and "cliente ausente" in alert.message
        assert snap.plan.version == 1 and snap.proposals == ()

    def test_a_vehicle_problem_is_critical(self) -> None:
        flow = day()
        flow.ws.driver.report(
            "V-01", "conductor", IncidentKind.VEHICLE_ISSUE, "Falla el freno", None
        )
        alert = next(a for a in flow.ws.snapshot.execute().alerts if a.code == "driver_report")
        assert alert.level == "critical"

    def test_the_driver_only_sees_their_own_reports(self) -> None:
        flow = day()
        flow.ws.driver.report("V-01", "c1", IncidentKind.OTHER, "Aviso uno", None)
        flow.ws.driver.report("V-02", "c2", IncidentKind.OTHER, "Aviso dos", None)
        assert [r.detail for r in flow.ws.driver.route("V-01").reports] == ["Aviso uno"]
        assert [r.detail for r in flow.ws.driver.route("V-02").reports] == ["Aviso dos"]

    @pytest.mark.parametrize("detail", ["", "ab", "   ", "x" * 301])
    def test_the_description_must_be_between_3_and_300_characters(self, detail: str) -> None:
        with pytest.raises(InvalidValueError, match="3 a 300"):
            day().ws.driver.report("V-01", "c", IncidentKind.OTHER, detail, None)

    def test_cannot_report_about_an_order_of_another_vehicle(self) -> None:
        flow = day()
        other = flow.ws.driver.route("V-02").stops[0].stop.order_id
        with pytest.raises(NotFoundError):
            flow.ws.driver.report("V-01", "c", IncidentKind.OTHER, "Algo ocurrió", other)
        assert flow.ws.core.repo.reports() == []

    def test_reports_are_numbered_and_stored_in_the_tenant_state(self) -> None:
        flow = day()
        a = flow.ws.driver.report("V-01", "c", IncidentKind.OTHER, "Primera novedad", None)
        b = flow.ws.driver.report("V-01", "c", IncidentKind.OTHER, "Segunda novedad", None)
        assert (a.id, b.id) == ("NV-001", "NV-002")
        assert [r.id for r in flow.ws.core.repo.reports()] == ["NV-001", "NV-002"]

    def test_restarting_the_day_clears_reports_and_confirmations(self) -> None:
        flow = day()
        flow.ws.driver.report("V-01", "c", IncidentKind.OTHER, "Una novedad", None)
        flow.ws.day.start("t")
        assert flow.ws.core.repo.reports() == [] and flow.ws.core.repo.confirmations() == {}
