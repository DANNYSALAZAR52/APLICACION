"""Seguridad y contrato HTTP del ruteo: RBAC, aislamiento entre empresas, entradas y auditoría."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from fleetplanner.adapters.inbound.http.routes_routing import StreamConfig
from fleetplanner.bootstrap.application import (
    Application,
    SeedCredential,
    build_http_app,
)
from tenancy_helpers import A, B, make_app, password_of

warnings.filterwarnings("ignore", message=".*httpx.*")

ROUTING = "/api/v1/routing"
CLOSURE = {
    "type": "road_closure",
    "label": "Calle 80",
    "lat": 4.722,
    "lon": -74.10,
    "radius_km": 2.5,
    "factor": 2.5,
    "duration_min": 120,
}


@dataclass
class Ctx:
    app: Application
    creds: list[SeedCredential]
    client: TestClient

    def headers(self, tenant: str | None, username: str) -> dict[str, str]:
        key = tenant if tenant else "(sin empresa)"
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": tenant,
                "username": username,
                "password": password_of(self.creds, key, username),
            },
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def dispatcher(self, tenant: str = A) -> dict[str, str]:
        return self.headers(tenant, "despachador")


@pytest.fixture
def ctx() -> Ctx:
    app, creds, _ = make_app()
    return Ctx(app, creds, TestClient(build_http_app(app), raise_server_exceptions=False))


def _code(response) -> str:  # type: ignore[no-untyped-def]
    return response.json()["error"]["codigo"]  # type: ignore[no-any-return]


class TestAuthentication:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/tower"),
            ("post", "/track"),
            ("post", "/events"),
            ("post", "/simulation"),
            ("post", "/day/reset"),
            ("get", "/plans/1"),
            ("get", "/indicators"),
            ("get", "/stream"),
            ("get", "/driver/route"),
            ("post", "/driver/deliveries/P-001/confirm"),
            ("post", "/driver/reports"),
            ("post", "/proposals/PR-001/decision"),
        ],
    )
    def test_every_routing_endpoint_requires_a_token(
        self, ctx: Ctx, method: str, path: str
    ) -> None:
        response = getattr(ctx.client, method)(ROUTING + path)
        assert response.status_code == 401


class TestRoleMatrix:
    @pytest.mark.parametrize("username", ["gerencia", "conductor", "admin"])
    def test_roles_other_than_dispatcher_cannot_see_the_control_tower(
        self, ctx: Ctx, username: str
    ) -> None:
        response = ctx.client.get(f"{ROUTING}/tower", headers=ctx.headers(A, username))
        assert response.status_code == 403 and _code(response) == "PERMISO_DENEGADO"

    def test_superadmin_has_no_company_and_cannot_use_routing(self, ctx: Ctx) -> None:
        response = ctx.client.get(f"{ROUTING}/tower", headers=ctx.headers(None, "superadmin"))
        assert response.status_code == 403

    @pytest.mark.parametrize("username", ["gerencia", "conductor", "admin"])
    def test_other_roles_cannot_inject_events_or_control_the_day(
        self, ctx: Ctx, username: str
    ) -> None:
        headers = ctx.headers(A, username)
        assert (
            ctx.client.post(f"{ROUTING}/events", json=CLOSURE, headers=headers).status_code == 403
        )
        assert ctx.client.post(f"{ROUTING}/day/reset", headers=headers).status_code == 403
        assert (
            ctx.client.post(
                f"{ROUTING}/simulation", json={"action": "pause"}, headers=headers
            ).status_code
            == 403
        )

    def test_denied_attempts_are_audited(self, ctx: Ctx) -> None:
        ctx.client.get(f"{ROUTING}/tower", headers=ctx.headers(A, "conductor"))
        events = ctx.app.audit.list_events(None, 50)
        assert any(e.action == "routing.tower.view" and e.outcome.value == "denied" for e in events)

    def test_dispatcher_can_read_and_operate(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        assert ctx.client.get(f"{ROUTING}/tower", headers=headers).status_code == 200
        assert ctx.client.post(f"{ROUTING}/track", headers=headers).status_code == 200


class TestTowerContract:
    def test_snapshot_is_labelled_as_demo_and_starts_paused_at_0500(self, ctx: Ctx) -> None:
        body = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher()).json()
        assert body["demo_label"] == "DATOS DE DEMOSTRACIÓN"
        assert body["clock"]["paused"] is True and body["clock"]["simulated"] is True
        assert body["clock"]["minute"] == 300
        assert body["plan"]["version"] == 1
        assert {v["route_status"] for v in body["vehicles"]} == {"active", "standby"}
        assert body["travel_notice"] is None

    def test_snapshot_never_contains_secrets_or_internal_paths(self, ctx: Ctx) -> None:
        text = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher()).text.lower()
        for forbidden in ("password", "token", "secret", "traceback", "c:\\\\"):
            assert forbidden not in text

    def test_responses_are_not_cacheable(self, ctx: Ctx) -> None:
        response = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher())
        assert response.headers["cache-control"] == "no-store"


class TestTenantIsolation:
    def test_each_company_sees_its_own_fleet_and_orders(self, ctx: Ctx) -> None:
        a = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher(A)).json()
        b = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher(B)).json()
        assert len(a["customers"]) == 8 and len(b["customers"]) == 5
        assert a["stops"] != b["stops"]

    def test_an_event_in_one_company_does_not_leak_into_the_other(self, ctx: Ctx) -> None:
        headers_a, headers_b = ctx.dispatcher(A), ctx.dispatcher(B)
        ctx.client.get(f"{ROUTING}/tower", headers=headers_b)
        created = ctx.client.post(f"{ROUTING}/events", json=CLOSURE, headers=headers_a)
        assert created.status_code == 201
        b = ctx.client.get(f"{ROUTING}/tower", headers=headers_b).json()
        assert b["events"] == [] and b["proposals"] == []
        a = ctx.client.get(f"{ROUTING}/tower", headers=headers_a).json()
        assert len(a["events"]) == 1

    def test_a_proposal_of_another_company_is_not_found(self, ctx: Ctx) -> None:
        headers_a, headers_b = ctx.dispatcher(A), ctx.dispatcher(B)
        ctx.client.get(f"{ROUTING}/tower", headers=headers_b)
        ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "advance", "value": 90}, headers=headers_a
        )
        proposal = ctx.client.post(f"{ROUTING}/events", json=CLOSURE, headers=headers_a).json()[
            "proposal"
        ]
        response = ctx.client.post(
            f"{ROUTING}/proposals/{proposal['id']}/decision",
            json={"decision": "approve"},
            headers=headers_b,
        )
        assert response.status_code in (404, 409)
        assert ctx.client.get(f"{ROUTING}/plans/2", headers=headers_b).status_code == 404

    def test_simulation_clock_is_independent_per_company(self, ctx: Ctx) -> None:
        ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher(A))
        ctx.client.post(
            f"{ROUTING}/simulation",
            json={"action": "advance", "value": 120},
            headers=ctx.dispatcher(A),
        )
        a = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher(A)).json()["clock"]["minute"]
        b = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher(B)).json()["clock"]["minute"]
        assert a == 420 and b == 300

    def test_tenant_id_in_the_body_is_rejected(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            f"{ROUTING}/events",
            json={**CLOSURE, "tenant_id": "t-empresa-demo-b"},
            headers=ctx.dispatcher(),
        )
        assert response.status_code == 422


class TestEventValidation:
    def test_latitude_40_is_rejected_with_an_explanation_in_spanish(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            f"{ROUTING}/events", json={**CLOSURE, "lat": 40}, headers=ctx.dispatcher()
        )
        assert response.status_code == 422
        assert "fuera de Colombia" in response.json()["error"]["mensaje"]

    @pytest.mark.parametrize(
        "patch",
        [
            {"radius_km": 0},
            {"radius_km": 500},
            {"factor": 0.5},
            {"duration_min": -5},
            {"label": ""},
            {"type": "inventado"},
        ],
    )
    def test_out_of_range_closure_values_are_rejected(
        self, ctx: Ctx, patch: dict[str, object]
    ) -> None:
        response = ctx.client.post(
            f"{ROUTING}/events", json={**CLOSURE, **patch}, headers=ctx.dispatcher()
        )
        assert response.status_code == 422

    def test_inverted_window_14_00_to_10_00_is_rejected_with_an_explanation(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "advance", "value": 60}, headers=headers
        )
        response = ctx.client.post(
            f"{ROUTING}/events",
            json={
                "type": "urgent_order",
                "customer_code": "C-001",
                "kg": 200,
                "m3": 1,
                "window_start": "14:00",
                "window_end": "10:00",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "posterior" in response.json()["error"]["mensaje"]

    def test_malformed_clock_text_is_rejected(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            f"{ROUTING}/events",
            json={
                "type": "window_change",
                "order_id": "P-001",
                "window_start": "ab:cd",
                "window_end": "10:00",
            },
            headers=ctx.dispatcher(),
        )
        assert response.status_code == 422

    def test_unknown_vehicle_is_404_and_leaves_no_event(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        response = ctx.client.post(
            f"{ROUTING}/events", json={"type": "breakdown", "vehicle_id": "V-99"}, headers=headers
        )
        assert response.status_code == 404
        assert ctx.client.get(f"{ROUTING}/tower", headers=headers).json()["events"] == []

    @pytest.mark.parametrize("bad", ["../etc", "PR 1", "x" * 40, "%00"])
    def test_proposal_ids_in_the_path_are_validated(self, ctx: Ctx, bad: str) -> None:
        response = ctx.client.post(
            f"{ROUTING}/proposals/{bad}/decision",
            json={"decision": "approve"},
            headers=ctx.dispatcher(),
        )
        assert response.status_code in (404, 422)

    def test_simulation_speed_outside_the_allowed_list_is_rejected(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "speed", "value": 7}, headers=ctx.dispatcher()
        )
        assert response.status_code == 422
        assert "Velocidad no permitida" in response.json()["error"]["mensaje"]


class TestFlowOverHttp:
    def test_event_then_approval_creates_a_new_plan_version(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "advance", "value": 90}, headers=headers
        )
        created = ctx.client.post(
            f"{ROUTING}/events",
            json={"type": "breakdown", "vehicle_id": "V-01"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        proposal = created.json()["proposal"]
        assert proposal["status"] == "pending" and proposal["requires_confirmation"] is True
        assert proposal["impact"]["activates_reserve"] is True and proposal["routes"]
        decision = ctx.client.post(
            f"{ROUTING}/proposals/{proposal['id']}/decision",
            json={"decision": "approve", "comment": "ok"},
            headers=headers,
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["plan_version"] == 2
        tower = ctx.client.get(f"{ROUTING}/tower", headers=headers).json()
        assert tower["plan"]["version"] == 2 and len(tower["versions"]) == 2
        detail = ctx.client.get(f"{ROUTING}/plans/1", headers=headers).json()
        assert detail["summary"]["version"] == 1

    def test_decisions_and_events_are_audited_with_the_actor(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "advance", "value": 90}, headers=headers
        )
        proposal = ctx.client.post(
            f"{ROUTING}/events", json={"type": "breakdown", "vehicle_id": "V-01"}, headers=headers
        ).json()["proposal"]
        ctx.client.post(
            f"{ROUTING}/proposals/{proposal['id']}/decision",
            json={"decision": "reject"},
            headers=headers,
        )
        actions = {
            e.action
            for e in ctx.app.audit.list_events(None, 100)
            if e.actor_username == "despachador"
        }
        assert {"routing.event.inject", "routing.proposal.reject", "routing.sim.control"} <= actions

    def test_provider_failure_toggle_shows_the_notice(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        body = ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "provider", "value": 0}, headers=headers
        ).json()
        assert body["travel_notice"] == "Tiempos estimados sin tráfico"
        assert body["provider_available"] is False

    def test_day_reset_restores_version_1_and_pauses_the_clock(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "advance", "value": 90}, headers=headers
        )
        ctx.client.post(f"{ROUTING}/events", json=CLOSURE, headers=headers)
        body = ctx.client.post(f"{ROUTING}/day/reset", headers=headers).json()
        assert body["plan"]["version"] == 1 and body["events"] == []
        assert body["clock"]["minute"] == 300 and body["clock"]["paused"] is True


class TestRateLimit:
    def test_too_many_events_in_a_minute_are_throttled(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        statuses = [
            ctx.client.post(
                f"{ROUTING}/events", json={**CLOSURE, "lat": 4.6, "lon": -74.0}, headers=headers
            ).status_code
            for _ in range(32)
        ]
        assert 429 in statuses
        assert statuses.count(201) == 30


class TestIndicators:
    @pytest.mark.parametrize("username", ["gerencia", "despachador"])
    def test_management_and_dispatch_can_read_the_indicators(self, ctx: Ctx, username: str) -> None:
        response = ctx.client.get(f"{ROUTING}/indicators", headers=ctx.headers(A, username))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["demo_label"] == "DATOS DE DEMOSTRACIÓN"
        assert [s["key"] for s in body["scenarios"]] == [
            "clean",
            "static_events",
            "dynamic_events",
            "dynamic_incomplete",
        ]
        assert any("Puntualidad =" in d for d in body["definitions"])
        assert any("OTIF =" in d for d in body["definitions"])

    @pytest.mark.parametrize("username", ["conductor", "admin"])
    def test_driver_and_tenant_admin_cannot(self, ctx: Ctx, username: str) -> None:
        response = ctx.client.get(f"{ROUTING}/indicators", headers=ctx.headers(A, username))
        assert response.status_code == 403

    def test_superadmin_cannot(self, ctx: Ctx) -> None:
        response = ctx.client.get(f"{ROUTING}/indicators", headers=ctx.headers(None, "superadmin"))
        assert response.status_code == 403

    def test_each_company_gets_its_own_denominators(self, ctx: Ctx) -> None:
        a = ctx.client.get(f"{ROUTING}/indicators", headers=ctx.dispatcher(A)).json()
        b = ctx.client.get(f"{ROUTING}/indicators", headers=ctx.dispatcher(B)).json()
        assert a["scenarios"][0]["kpis"]["committed_orders"] == 8
        assert b["scenarios"][0]["kpis"]["committed_orders"] == 5
        assert a["live"]["projected"]["committed_orders"] == 8

    def test_scenarios_do_not_change_the_live_day(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        before = ctx.client.get(f"{ROUTING}/tower", headers=headers).json()
        ctx.client.get(f"{ROUTING}/indicators", headers=headers)
        after = ctx.client.get(f"{ROUTING}/tower", headers=headers).json()
        assert after["plan"]["version"] == before["plan"]["version"] == 1
        assert after["events"] == [] and after["clock"]["minute"] == before["clock"]["minute"]

    def test_live_projection_is_a_number_between_zero_and_one(self, ctx: Ctx) -> None:
        body = ctx.client.get(f"{ROUTING}/indicators", headers=ctx.dispatcher()).json()
        projected = body["live"]["projected"]
        assert 0 <= projected["otif"] <= projected["punctuality"] <= 1


@pytest.fixture
def streaming() -> Ctx:
    app, creds, _ = make_app()
    config = StreamConfig(max_seconds=0.6, tick_seconds=0.05, ping_seconds=0.2, max_per_user=2)
    http = build_http_app(app, stream=config)
    return Ctx(app, creds, TestClient(http, raise_server_exceptions=False))


def _read_stream(ctx: Ctx, headers: dict[str, str]) -> tuple[int, str, str]:
    with ctx.client.stream("GET", f"{ROUTING}/stream", headers=headers) as response:
        body = "".join(response.iter_text())
        return response.status_code, response.headers.get("content-type", ""), body


def _events(body: str) -> list[tuple[str, str]]:
    found = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if line and not line.startswith(":")]
        name = next((ln[7:] for ln in lines if ln.startswith("event: ")), "")
        data = next((ln[6:] for ln in lines if ln.startswith("data: ")), "")
        if name:
            found.append((name, data))
    return found


class TestRealTimeStream:
    def test_dispatcher_receives_the_snapshot_and_the_stream_renews_itself(
        self, streaming: Ctx
    ) -> None:
        status, ctype, body = _read_stream(streaming, streaming.dispatcher())
        assert status == 200 and ctype.startswith("text/event-stream")
        events = _events(body)
        assert events[0][0] == "snapshot"
        first = json.loads(events[0][1])
        assert first["demo_label"] == "DATOS DE DEMOSTRACIÓN" and first["plan"]["version"] == 1
        assert events[-1] == ("end", '{"reason": "renew"}')

    @pytest.mark.parametrize("username", ["gerencia", "conductor", "admin"])
    def test_other_roles_cannot_open_the_stream(self, streaming: Ctx, username: str) -> None:
        status, _, _ = _read_stream(streaming, streaming.headers(A, username))
        assert status == 403

    def test_without_a_token_it_is_401_and_a_logged_out_token_stops_working(
        self, streaming: Ctx
    ) -> None:
        assert streaming.client.get(f"{ROUTING}/stream").status_code == 401
        headers = streaming.dispatcher()
        streaming.client.post("/api/v1/auth/logout", headers=headers)
        status, _, _ = _read_stream(streaming, headers)
        assert status == 401

    def test_each_company_only_receives_its_own_state(self, streaming: Ctx) -> None:
        _, _, a = _read_stream(streaming, streaming.dispatcher(A))
        _, _, b = _read_stream(streaming, streaming.dispatcher(B))
        snap_a = json.loads(_events(a)[0][1])
        snap_b = json.loads(_events(b)[0][1])
        assert len(snap_a["customers"]) == 8 and len(snap_b["customers"]) == 5
        assert not {o for o, _ in snap_b["pending_orders"]} - {
            "P-001",
            "P-002",
            "P-003",
            "P-004",
            "P-005",
        }
        assert "Empresa Demo B" not in a and "empresa-demo-b" not in a

    def test_changes_are_pushed_and_idle_connections_get_keepalive_pings(
        self, streaming: Ctx
    ) -> None:
        headers = streaming.dispatcher()
        streaming.client.get(f"{ROUTING}/tower", headers=headers)
        _, _, body = _read_stream(streaming, headers)
        assert body.count("event: snapshot") == 1  # nada cambió: solo el primero
        assert ": ping" in body

    def test_the_number_of_simultaneous_streams_per_user_is_limited(self) -> None:
        app, creds, _ = make_app()
        config = StreamConfig(max_seconds=0.3, tick_seconds=0.05, max_per_user=0)
        ctx = Ctx(
            app,
            creds,
            TestClient(build_http_app(app, stream=config), raise_server_exceptions=False),
        )
        response = ctx.client.get(f"{ROUTING}/stream", headers=ctx.dispatcher())
        assert response.status_code == 429


class TestGpsSignalControl:
    def body(self, **extra: object) -> dict[str, object]:
        return {"action": "gps_signal", "value": 0, "target": "V-01", **extra}

    def test_dispatcher_can_cut_and_restore_a_vehicle_signal(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        cut = ctx.client.post(f"{ROUTING}/simulation", json=self.body(), headers=headers).json()
        assert next(v for v in cut["vehicles"] if v["id"] == "V-01")["gps_signal_enabled"] is False
        back = ctx.client.post(
            f"{ROUTING}/simulation", json=self.body(value=1), headers=headers
        ).json()
        assert next(v for v in back["vehicles"] if v["id"] == "V-01")["gps_signal_enabled"] is True

    def test_it_needs_a_known_vehicle(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        missing = {"action": "gps_signal", "value": 0}
        assert (
            ctx.client.post(f"{ROUTING}/simulation", json=missing, headers=headers).status_code
            == 422
        )
        unknown = ctx.client.post(
            f"{ROUTING}/simulation", json=self.body(target="V-99"), headers=headers
        )
        assert unknown.status_code == 404

    @pytest.mark.parametrize("username", ["gerencia", "conductor", "admin"])
    def test_other_roles_cannot(self, ctx: Ctx, username: str) -> None:
        response = ctx.client.post(
            f"{ROUTING}/simulation", json=self.body(), headers=ctx.headers(A, username)
        )
        assert response.status_code == 403

    def test_the_vehicle_of_another_company_cannot_be_targeted(self, ctx: Ctx) -> None:
        headers_b = ctx.dispatcher(B)
        ctx.client.get(f"{ROUTING}/tower", headers=headers_b)
        # B solo tiene V-01..V-02 (+reserva/tercero); "V-05" existe en otras empresas pero no en B
        response = ctx.client.post(
            f"{ROUTING}/simulation", json=self.body(target="V-05"), headers=headers_b
        )
        assert response.status_code == 404

    def test_the_snapshot_exposes_gps_age_and_status(self, ctx: Ctx) -> None:
        headers = ctx.dispatcher()
        ctx.client.post(
            f"{ROUTING}/simulation", json={"action": "advance", "value": 150}, headers=headers
        )
        vehicles = ctx.client.get(f"{ROUTING}/tower", headers=headers).json()["vehicles"]
        active = [v for v in vehicles if v["route_status"] == "active"]
        assert active and all(v["gps_status"] in {"ok", "n/a"} for v in active)


class TestDriverApi:
    def driver(self, ctx: Ctx, tenant: str = A) -> dict[str, str]:
        return ctx.headers(tenant, "conductor")

    def advance(self, ctx: Ctx, minutes: int = 240) -> None:
        ctx.client.post(
            f"{ROUTING}/simulation",
            json={"action": "advance", "value": minutes},
            headers=ctx.dispatcher(),
        )

    def test_driver_sees_only_their_route_with_google_maps_links(self, ctx: Ctx) -> None:
        response = ctx.client.get(f"{ROUTING}/driver/route", headers=self.driver(ctx))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["demo_label"] == "DATOS DE DEMOSTRACIÓN"
        assert body["vehicle_id"] == "V-01" and body["stops"]
        assert {d["stop"]["vehicle_id"] for d in body["stops"]} == {"V-01"}
        link = body["nav_links"][0]["url"]
        assert link.startswith("https://www.google.com/maps/dir/?api=1") and "key=" not in link

    @pytest.mark.parametrize("username", ["despachador", "gerencia", "admin"])
    def test_other_roles_cannot_use_the_driver_endpoints(self, ctx: Ctx, username: str) -> None:
        headers = ctx.headers(A, username)
        assert ctx.client.get(f"{ROUTING}/driver/route", headers=headers).status_code == 403
        assert (
            ctx.client.post(
                f"{ROUTING}/driver/deliveries/P-001/confirm", headers=headers
            ).status_code
            == 403
        )
        body = {"kind": "other", "detail": "Algo ocurrió"}
        assert (
            ctx.client.post(f"{ROUTING}/driver/reports", json=body, headers=headers).status_code
            == 403
        )

    def test_superadmin_cannot(self, ctx: Ctx) -> None:
        headers = ctx.headers(None, "superadmin")
        assert ctx.client.get(f"{ROUTING}/driver/route", headers=headers).status_code == 403

    def test_the_driver_cannot_use_dispatcher_endpoints(self, ctx: Ctx) -> None:
        headers = self.driver(ctx)
        assert ctx.client.get(f"{ROUTING}/tower", headers=headers).status_code == 403
        assert (
            ctx.client.post(f"{ROUTING}/events", json=CLOSURE, headers=headers).status_code == 403
        )
        assert ctx.client.get(f"{ROUTING}/stream", headers=headers).status_code == 403

    def test_a_driver_without_an_assigned_vehicle_is_denied_and_audited(self, ctx: Ctx) -> None:
        from dataclasses import replace

        user = ctx.app.users.find_by_login(ctx.app.tenants.get_by_slug(A).id, "conductor")
        ctx.app.users.save(replace(user, attributes={}))
        response = ctx.client.get(f"{ROUTING}/driver/route", headers=self.driver(ctx))
        assert (
            response.status_code == 403
            and "vehículo asignado" in response.json()["error"]["mensaje"]
        )
        assert any(
            e.action == "routing.driver.view" and e.outcome.value == "denied"
            for e in ctx.app.audit.list_events(None, 50)
        )

    def test_the_vehicle_cannot_be_chosen_by_the_client(self, ctx: Ctx) -> None:
        headers = self.driver(ctx)
        body = {"kind": "other", "detail": "Algo ocurrió", "vehicle_id": "V-02"}
        assert (
            ctx.client.post(f"{ROUTING}/driver/reports", json=body, headers=headers).status_code
            == 422
        )
        assert (
            ctx.client.get(f"{ROUTING}/driver/route?vehicle_id=V-02", headers=headers).json()[
                "vehicle_id"
            ]
            == "V-01"
        )

    def test_confirm_delivery_after_arriving_and_it_is_audited(self, ctx: Ctx) -> None:
        headers = self.driver(ctx)
        order = ctx.client.get(f"{ROUTING}/driver/route", headers=headers).json()["stops"][0][
            "stop"
        ]["order_id"]
        early = ctx.client.post(f"{ROUTING}/driver/deliveries/{order}/confirm", headers=headers)
        assert early.status_code == 409 and "Aún no llega" in early.json()["error"]["mensaje"]
        self.advance(ctx)
        done = ctx.client.post(f"{ROUTING}/driver/deliveries/{order}/confirm", headers=headers)
        assert done.status_code == 200, done.text
        assert done.json()["source"] in {"driver", "geofence"}
        again = ctx.client.post(f"{ROUTING}/driver/deliveries/{order}/confirm", headers=headers)
        assert again.json()["already_confirmed"] is True
        actions = {
            e.action
            for e in ctx.app.audit.list_events(None, 100)
            if e.actor_username == "conductor"
        }
        assert "routing.delivery.confirm" in actions

    def test_cannot_confirm_the_order_of_another_vehicle_or_company(self, ctx: Ctx) -> None:
        tower_other = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher()).json()
        other_order = next(s["order_id"] for s in tower_other["stops"] if s["vehicle_id"] == "V-02")
        self.advance(ctx)
        headers = self.driver(ctx)
        assert (
            ctx.client.post(
                f"{ROUTING}/driver/deliveries/{other_order}/confirm", headers=headers
            ).status_code
            == 404
        )
        # el conductor de la empresa B tampoco puede tocar pedidos de A
        b_headers = self.driver(ctx, B)
        assert ctx.client.post(
            f"{ROUTING}/driver/deliveries/{other_order}/confirm", headers=b_headers
        ).status_code in (404, 409)

    def test_report_appears_to_the_dispatcher_and_not_to_the_other_company(self, ctx: Ctx) -> None:
        created = ctx.client.post(
            f"{ROUTING}/driver/reports",
            json={"kind": "customer_absent", "detail": "Nadie atiende en el cliente"},
            headers=self.driver(ctx),
        )
        assert created.status_code == 201, created.text
        tower = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher()).json()
        assert [r["detail"] for r in tower["reports"]] == ["Nadie atiende en el cliente"]
        assert any(a["code"] == "driver_report" for a in tower["alerts"])
        other = ctx.client.get(f"{ROUTING}/tower", headers=ctx.dispatcher(B)).json()
        assert other["reports"] == []

    @pytest.mark.parametrize(
        "body",
        [
            {"kind": "inventada", "detail": "Algo ocurrió"},
            {"kind": "other", "detail": "ab"},
            {"kind": "other", "detail": "x" * 301},
            {"kind": "other"},
        ],
    )
    def test_invalid_reports_are_rejected(self, ctx: Ctx, body: dict[str, object]) -> None:
        response = ctx.client.post(f"{ROUTING}/driver/reports", json=body, headers=self.driver(ctx))
        assert response.status_code == 422

    def test_reports_are_rate_limited(self, ctx: Ctx) -> None:
        headers = self.driver(ctx)
        body = {"kind": "other", "detail": "Aviso repetido"}
        statuses = [
            ctx.client.post(f"{ROUTING}/driver/reports", json=body, headers=headers).status_code
            for _ in range(22)
        ]
        assert statuses.count(201) == 20 and 429 in statuses

    @pytest.mark.parametrize("bad", ["../etc", "P 1", "x" * 40])
    def test_order_ids_in_the_path_are_validated(self, ctx: Ctx, bad: str) -> None:
        response = ctx.client.post(
            f"{ROUTING}/driver/deliveries/{bad}/confirm", headers=self.driver(ctx)
        )
        assert response.status_code in (404, 422)
