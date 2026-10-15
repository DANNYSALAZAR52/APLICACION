"""Seguridad y contrato HTTP de patrones de ML: RBAC, aislamiento, límites y auditoría."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from fleetplanner.bootstrap.application import Application, SeedCredential, build_http_app
from tenancy_helpers import A, B, make_app, password_of

warnings.filterwarnings("ignore", message=".*httpx.*")

P = "/api/v1/patterns"


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


@pytest.fixture
def ctx() -> Ctx:
    app, creds, _ = make_app(ml=True)
    return Ctx(app, creds, TestClient(build_http_app(app), raise_server_exceptions=False))


class TestAccess:
    @pytest.mark.parametrize(("method", "path"), [("get", ""), ("post", "/retrain")])
    def test_requires_a_token(self, ctx: Ctx, method: str, path: str) -> None:
        assert getattr(ctx.client, method)(P + path).status_code == 401

    @pytest.mark.parametrize("username", ["gerencia", "despachador"])
    def test_management_and_dispatcher_can_read(self, ctx: Ctx, username: str) -> None:
        response = ctx.client.get(P, headers=ctx.headers(A, username))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["demo_label"] == "DATOS DE DEMOSTRACIÓN"
        assert "SINTÉTICOS" in body["provenance"]

    @pytest.mark.parametrize("username", ["conductor", "admin"])
    def test_other_roles_are_denied(self, ctx: Ctx, username: str) -> None:
        assert ctx.client.get(P, headers=ctx.headers(A, username)).status_code == 403

    def test_superadmin_has_no_company_and_is_denied(self, ctx: Ctx) -> None:
        assert ctx.client.get(P, headers=ctx.headers(None, "superadmin")).status_code == 403

    @pytest.mark.parametrize("username", ["despachador", "conductor", "admin"])
    def test_only_management_can_retrain(self, ctx: Ctx, username: str) -> None:
        response = ctx.client.post(P + "/retrain", headers=ctx.headers(A, username))
        assert response.status_code == 403

    def test_denials_are_audited(self, ctx: Ctx) -> None:
        ctx.client.get(P, headers=ctx.headers(A, "conductor"))
        denied = [e for e in ctx.app.audit.list_events(None, 500) if e.action == "patterns.view"]
        assert any(e.outcome.value == "denied" for e in denied)


class TestContract:
    def test_report_has_models_with_provenance_and_no_artifact_bytes(self, ctx: Ctx) -> None:
        body = ctx.client.get(P, headers=ctx.headers(A, "gerencia")).json()
        assert [m["name"] for m in body["models"]] == [
            "pronostico_demanda",
            "deteccion_anomalias",
            "riesgo_retraso",
            "segmentacion_clientes",
        ]
        for model in body["models"]:
            assert model["version"] == 1
            assert len(model["artifact_sha256"]) == 64
            assert model["library"].startswith("scikit-learn")
            assert "payload" not in model
        assert body["limits"]
        assert all(len(f["forecast"]) == 7 for f in body["forecasts"])
        assert all(a["message"] for a in body["anomalies"])
        assert all(0 <= d["probability"] <= 1 for d in body["delay_risks"])

    def test_dashboard_includes_ml_forecast_for_the_same_company(self, ctx: Ctx) -> None:
        body = ctx.client.get(
            "/api/v1/capacity/dashboard", headers=ctx.headers(A, "gerencia")
        ).json()
        assert body["ml_forecast_available"] is True
        assert {row["corridor_code"] for row in body["ml_forecast"]} == {"C1", "C2", "C3"}

    def test_retrain_creates_a_new_version_and_is_audited_with_the_versions(self, ctx: Ctx) -> None:
        headers = ctx.headers(A, "gerencia")
        ctx.client.get(P, headers=headers)
        response = ctx.client.post(P + "/retrain", headers=headers)
        assert response.status_code == 200
        assert {m["version"] for m in response.json()["models"]} == {2}
        audited = [
            e for e in ctx.app.audit.list_events(None, 500) if e.action == "patterns.retrain"
        ]
        assert audited and audited[0].outcome.value == "success"
        assert "pronostico_demanda:v2" in audited[0].detail["versiones"]

    def test_retraining_is_rate_limited(self, ctx: Ctx) -> None:
        headers = ctx.headers(A, "gerencia")
        statuses = [ctx.client.post(P + "/retrain", headers=headers).status_code for _ in range(4)]
        assert statuses == [200, 200, 200, 429]


class TestIsolation:
    def test_each_company_sees_only_its_own_results(self, ctx: Ctx) -> None:
        a = ctx.client.get(P, headers=ctx.headers(A, "gerencia")).json()
        b = ctx.client.get(P, headers=ctx.headers(B, "gerencia")).json()
        customers_a = {c for s in a["segments"] for c in s["customers"]}
        customers_b = {c for s in b["segments"] for c in s["customers"]}
        assert len(customers_a) == 12 and len(customers_b) == 10
        assert a["provenance"] != b["provenance"]
        assert {m["artifact_sha256"] for m in a["models"]}.isdisjoint(
            {m["artifact_sha256"] for m in b["models"]}
        )

    def test_a_tenant_in_the_query_or_header_is_ignored(self, ctx: Ctx) -> None:
        headers = {**ctx.headers(A, "gerencia"), "X-Tenant-Id": "t-" + B}
        plain = ctx.client.get(P, headers=ctx.headers(A, "gerencia")).json()
        spoofed = ctx.client.get(P + f"?tenant_id=t-{B}&tenant_slug={B}", headers=headers).json()
        assert spoofed["provenance"] == plain["provenance"]
        assert {m["artifact_sha256"] for m in spoofed["models"]} == {
            m["artifact_sha256"] for m in plain["models"]
        }

    def test_retraining_one_company_does_not_touch_the_other(self, ctx: Ctx) -> None:
        a_headers, b_headers = ctx.headers(A, "gerencia"), ctx.headers(B, "gerencia")
        ctx.client.get(P, headers=b_headers)
        ctx.client.post(P + "/retrain", headers=a_headers)
        b = ctx.client.get(P, headers=b_headers).json()
        assert {m["version"] for m in b["models"]} == {1}

    def test_suspended_company_cannot_read_patterns(self, ctx: Ctx) -> None:
        headers = ctx.headers(A, "gerencia")
        sa = ctx.headers(None, "superadmin")
        assert ctx.client.post(f"/api/v1/tenants/{A}/suspend", headers=sa).status_code == 200
        assert ctx.client.get(P, headers=headers).status_code in (401, 403)


class TestWithoutMl:
    def test_a_company_without_models_gets_404_not_a_crash(self) -> None:
        app, creds, _ = make_app(ml=False)
        client = TestClient(build_http_app(app), raise_server_exceptions=False)
        login = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": A,
                "username": "gerencia",
                "password": password_of(creds, A, "gerencia"),
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get(P, headers=headers).status_code == 404
