"""Seguridad de la API HTTP: autenticación, RBAC, aislamiento entre tenants y cabeceras."""

from __future__ import annotations

import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from fleetplanner.adapters.outbound.clock import FixedClock
from fleetplanner.bootstrap.application import (
    Application,
    SeedCredential,
    build_application,
    build_http_app,
    seed_demo,
)
from fleetplanner.bootstrap.settings import load_settings
from tenancy_helpers import NOW, SIGNING_KEY, A, B, FakeHasher, make_app, password_of

warnings.filterwarnings("ignore", message=".*httpx.*")


@dataclass
class Ctx:
    app: Application
    creds: list[SeedCredential]
    clock: FixedClock
    client: TestClient

    def login(self, tenant: str | None, username: str, password: str | None = None):  # type: ignore[no-untyped-def]
        key = tenant if tenant else "(sin empresa)"
        body = {
            "tenant_slug": tenant,
            "username": username,
            "password": password or password_of(self.creds, key, username),
        }
        return self.client.post("/api/v1/auth/login", json=body)

    def token(self, tenant: str | None, username: str) -> str:
        response = self.login(tenant, username)
        assert response.status_code == 200, response.text
        return str(response.json()["access_token"])

    def headers(self, tenant: str | None, username: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(tenant, username)}"}


@pytest.fixture
def ctx() -> Ctx:
    app, creds, clock = make_app()
    client = TestClient(build_http_app(app), raise_server_exceptions=False)
    return Ctx(app, creds, clock, client)


def _error(response) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return response.json()["error"]  # type: ignore[no-any-return]


class TestAuthentication:
    def test_login_returns_token_user_and_a_hardened_refresh_cookie(self, ctx: Ctx) -> None:
        response = ctx.login(A, "gerencia")
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"  # noqa: S105 - esquema OAuth, no una contraseña
        assert body["user"]["role"] == "management"
        assert body["user"]["tenant_slug"] == A
        assert "capacity:read" in body["user"]["permissions"]
        assert "password" not in response.text.lower().replace("password_hash", "")
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert "path=/api/v1/auth" in cookie
        assert "fp_refresh=" in cookie

    def test_refresh_token_is_never_in_the_json_body(self, ctx: Ctx) -> None:
        body = ctx.login(A, "gerencia").json()
        assert "refresh" not in " ".join(body.keys()).lower()

    def test_login_rejects_unknown_fields_such_as_tenant_id(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": A,
                "tenant_id": "t-empresa-demo-b",
                "username": "gerencia",
                "password": password_of(ctx.creds, A, "gerencia"),
            },
        )
        assert response.status_code == 422
        assert _error(response)["codigo"] == "SOLICITUD_INVALIDA"

    def test_wrong_password_and_unknown_user_are_indistinguishable(self, ctx: Ctx) -> None:
        wrong = ctx.login(A, "gerencia", "mala-clave-2026")
        unknown = ctx.login(A, "fantasma", "mala-clave-2026")
        assert wrong.status_code == unknown.status_code == 401
        assert _error(wrong)["mensaje"] == _error(unknown)["mensaje"]
        assert _error(wrong)["codigo"] == "AUTENTICACION_INVALIDA"

    def test_password_is_not_echoed_in_validation_errors(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            "/api/v1/auth/login", json={"username": "", "password": "secreto-123456"}
        )
        assert response.status_code == 422
        assert "secreto-123456" not in response.text

    def test_login_is_rate_limited(self, ctx: Ctx) -> None:
        statuses = [ctx.login(A, "despachador", "mala-clave-2026").status_code for _ in range(14)]
        assert 429 in statuses
        assert statuses[0] == 401

    def test_lockout_applies_over_http(self, ctx: Ctx) -> None:
        for _ in range(5):
            ctx.login(A, "conductor", "mala-clave-2026")
        assert ctx.login(A, "conductor").status_code in (401, 429)
        ctx.clock.advance(timedelta(minutes=2))
        assert ctx.login(A, "conductor").status_code == 200

    def test_cross_origin_login_is_refused(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            "/api/v1/auth/login",
            json={"username": "x", "password": "y"},
            headers={"Origin": "https://sitio-malicioso.example"},
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer   ", "Basic abc", "Token abc"])
    def test_protected_routes_require_a_bearer_token(self, ctx: Ctx, header: str | None) -> None:
        headers = {} if header is None else {"Authorization": header}
        response = ctx.client.get("/api/v1/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_tampered_forged_and_expired_tokens_are_rejected(self, ctx: Ctx) -> None:
        good = ctx.token(A, "gerencia")
        head, body, sig = good.split(".")
        forged_key = jwt.encode(
            {
                "iss": "fleetplanner",
                "sub": "u-empresa-demo-a-gerencia",
                "tid": "t-empresa-demo-a",
                "role": "management",
                "jti": "z",
                "iat": int(NOW.timestamp()),
                "exp": int(NOW.timestamp()) + 600,
            },
            "una-clave-que-no-es-la-del-servidor-1234567890",
            algorithm="HS256",
        )
        for token in (f"{head}.{body}.{sig[:-3]}abc", forged_key, "x.y.z"):
            response = ctx.client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 401
        ctx.clock.advance(timedelta(minutes=16))
        expired = ctx.client.get("/api/v1/me", headers={"Authorization": f"Bearer {good}"})
        assert expired.status_code == 401

    def test_logout_invalidates_access_and_refresh(self, ctx: Ctx) -> None:
        login = ctx.login(A, "gerencia")
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert ctx.client.get("/api/v1/me", headers=headers).status_code == 200
        assert ctx.client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert ctx.client.get("/api/v1/me", headers=headers).status_code == 401
        assert ctx.client.post("/api/v1/auth/refresh").status_code == 401

    def test_refresh_rotates_the_cookie_and_old_one_is_dead(self, ctx: Ctx) -> None:
        login = ctx.login(A, "gerencia")
        old_cookie = ctx.client.cookies.get("fp_refresh")
        refreshed = ctx.client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["user"]["username"] == "gerencia"
        new_cookie = ctx.client.cookies.get("fp_refresh")
        assert old_cookie and new_cookie and old_cookie != new_cookie
        replay = TestClient(build_http_app(ctx.app), raise_server_exceptions=False)
        replay.cookies.set("fp_refresh", old_cookie, path="/api/v1/auth")
        assert replay.post("/api/v1/auth/refresh").status_code == 401  # reutilización
        assert login.status_code == 200

    def test_refresh_without_cookie_is_unauthorized(self, ctx: Ctx) -> None:
        assert ctx.client.post("/api/v1/auth/refresh").status_code == 401


class TestRoleBasedAccess:
    @pytest.mark.parametrize(
        ("username", "expected"),
        [("gerencia", 200), ("admin", 200), ("despachador", 403), ("conductor", 403)],
    )
    def test_capacity_dashboard_by_role(self, ctx: Ctx, username: str, expected: int) -> None:
        response = ctx.client.get("/api/v1/capacity/dashboard", headers=ctx.headers(A, username))
        assert response.status_code == expected
        if expected == 403:
            assert _error(response)["codigo"] == "PERMISO_DENEGADO"

    def test_super_admin_cannot_see_company_capacity(self, ctx: Ctx) -> None:
        response = ctx.client.get(
            "/api/v1/capacity/dashboard", headers=ctx.headers(None, "superadmin")
        )
        assert response.status_code == 403

    def test_dashboard_requires_authentication(self, ctx: Ctx) -> None:
        assert ctx.client.get("/api/v1/capacity/dashboard").status_code == 401

    @pytest.mark.parametrize("username", ["gerencia", "despachador", "conductor", "admin"])
    def test_only_super_admin_reaches_tenant_administration(self, ctx: Ctx, username: str) -> None:
        headers = ctx.headers(A, username)
        assert ctx.client.get("/api/v1/tenants", headers=headers).status_code == 403
        assert (
            ctx.client.post(
                "/api/v1/tenants", headers=headers, json={"slug": "intruso", "name": "Intruso"}
            ).status_code
            == 403
        )
        assert ctx.client.post(f"/api/v1/tenants/{B}/suspend", headers=headers).status_code == 403
        assert (
            ctx.client.post(f"/api/v1/tenants/{B}/reactivate", headers=headers).status_code == 403
        )

    def test_audit_is_limited_to_admin_roles(self, ctx: Ctx) -> None:
        for username in ("gerencia", "despachador", "conductor"):
            assert (
                ctx.client.get("/api/v1/audit", headers=ctx.headers(A, username)).status_code == 403
            )
        assert ctx.client.get("/api/v1/audit", headers=ctx.headers(A, "admin")).status_code == 200


class TestTenantIsolation:
    def test_dashboard_payload_differs_per_tenant_and_is_labelled_as_demo(self, ctx: Ctx) -> None:
        a = ctx.client.get("/api/v1/capacity/dashboard", headers=ctx.headers(A, "gerencia")).json()
        b = ctx.client.get("/api/v1/capacity/dashboard", headers=ctx.headers(B, "gerencia")).json()
        assert a["demo_label"] == b["demo_label"] == "DATOS DE DEMOSTRACIÓN"
        assert a["totals"]["current"] != b["totals"]["current"]
        assert a["totals"]["balance"] != b["totals"]["balance"]
        assert a["monte_carlo"]["seed"] != b["monte_carlo"]["seed"]

    @pytest.mark.parametrize(
        ("query", "extra_headers"),
        [
            (f"?tenant_id=t-{B}", {}),
            (f"?tenant_slug={B}&tenant={B}", {}),
            ("", {"X-Tenant-Id": f"t-{B}"}),
            ("", {"X-Tenant": B, "X-Forwarded-Host": f"{B}.demo.local"}),
            (f"/../../{B}", {}),
        ],
    )
    def test_tenant_hints_from_the_client_are_ignored(
        self, ctx: Ctx, query: str, extra_headers: dict[str, str]
    ) -> None:
        headers = {**ctx.headers(A, "gerencia"), **extra_headers}
        own = ctx.client.get(
            "/api/v1/capacity/dashboard", headers=ctx.headers(A, "gerencia")
        ).json()
        other_b = ctx.client.get(
            "/api/v1/capacity/dashboard", headers=ctx.headers(B, "gerencia")
        ).json()
        response = ctx.client.get(f"/api/v1/capacity/dashboard{query}", headers=headers)
        if response.status_code == 200:  # parámetros extra: se ignoran y siguen siendo datos de A
            assert response.json()["totals"] == own["totals"]
            assert response.json()["totals"] != other_b["totals"]
        else:
            assert response.status_code == 404

    def test_a_token_with_a_swapped_tenant_claim_is_rejected(self, ctx: Ctx) -> None:
        """Aun conociendo la clave, el tenant del token debe coincidir con el del usuario."""
        now = int(NOW.timestamp())
        forged = jwt.encode(
            {
                "iss": "fleetplanner",
                "sub": "u-empresa-demo-a-gerencia",
                "tid": f"t-{B}",
                "role": "management",
                "jti": "forjado",
                "iat": now,
                "exp": now + 600,
            },
            SIGNING_KEY,
            algorithm="HS256",
        )
        response = ctx.client.get(
            "/api/v1/capacity/dashboard", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401

    def test_a_token_claiming_a_higher_role_is_rejected(self, ctx: Ctx) -> None:
        now = int(NOW.timestamp())
        forged = jwt.encode(
            {
                "iss": "fleetplanner",
                "sub": "u-empresa-demo-a-conductor",
                "tid": f"t-{A}",
                "role": "management",
                "jti": "forjado2",
                "iat": now,
                "exp": now + 600,
            },
            SIGNING_KEY,
            algorithm="HS256",
        )
        response = ctx.client.get(
            "/api/v1/capacity/dashboard", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401

    def test_user_of_one_tenant_cannot_login_through_the_other(self, ctx: Ctx) -> None:
        response = ctx.login(B, "gerencia", password_of(ctx.creds, A, "gerencia"))
        assert response.status_code == 401

    def test_concurrent_requests_from_both_tenants_do_not_mix(self, ctx: Ctx) -> None:
        headers = {A: ctx.headers(A, "gerencia"), B: ctx.headers(B, "gerencia")}
        expected = {
            t: ctx.client.get("/api/v1/capacity/dashboard", headers=h).json()["totals"]
            for t, h in headers.items()
        }
        assert expected[A] != expected[B]

        def fetch(tenant: str) -> tuple[str, dict[str, object]]:
            client = TestClient(build_http_app(ctx.app), raise_server_exceptions=False)
            data = client.get("/api/v1/capacity/dashboard", headers=headers[tenant]).json()
            return tenant, data["totals"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(fetch, [A, B] * 6))
        for tenant, totals in results:
            assert totals == expected[tenant]

    def test_company_audit_never_contains_other_company_events(self, ctx: Ctx) -> None:
        ctx.token(B, "gerencia")
        events = ctx.client.get("/api/v1/audit", headers=ctx.headers(A, "admin")).json()
        assert events
        tenant_ids = {e["tenant_id"] for e in events}
        assert tenant_ids == {f"t-{A}"}


class TestSuspension:
    def test_suspending_a_tenant_blocks_it_everywhere_and_spares_the_other(self, ctx: Ctx) -> None:
        a_headers = ctx.headers(A, "gerencia")
        a_login = ctx.login(A, "admin")
        admin_cookie = ctx.client.cookies.get("fp_refresh")
        assert admin_cookie
        sup = ctx.headers(None, "superadmin")  # esto reemplaza la cookie del cliente compartido
        assert ctx.client.post(f"/api/v1/tenants/{A}/suspend", headers=sup).status_code == 200

        blocked = ctx.client.get("/api/v1/capacity/dashboard", headers=a_headers)
        assert blocked.status_code == 403 and _error(blocked)["codigo"] == "EMPRESA_SUSPENDIDA"
        assert ctx.login(A, "gerencia").status_code == 403
        stale = TestClient(build_http_app(ctx.app), raise_server_exceptions=False)
        stale.cookies.set("fp_refresh", admin_cookie, path="/api/v1/auth")
        assert stale.post("/api/v1/auth/refresh").status_code == 401  # sesiones revocadas
        assert a_login.status_code == 200
        assert B not in blocked.text  # no se filtra información de la otra empresa
        assert (
            ctx.client.get(
                "/api/v1/capacity/dashboard", headers=ctx.headers(B, "gerencia")
            ).status_code
            == 200
        )

        assert ctx.client.post(f"/api/v1/tenants/{A}/reactivate", headers=sup).status_code == 200
        assert ctx.login(A, "gerencia").status_code == 200


class TestTenantAdministrationApi:
    def test_super_admin_lists_provisions_and_provision_is_idempotent(self, ctx: Ctx) -> None:
        sup = ctx.headers(None, "superadmin")
        listing = ctx.client.get("/api/v1/tenants", headers=sup).json()
        assert [t["slug"] for t in listing] == [A, B]
        assert all(
            "connection" not in str(t).lower() and "password" not in str(t).lower() for t in listing
        )

        created = ctx.client.post(
            "/api/v1/tenants", headers=sup, json={"slug": "empresa-c", "name": "Empresa C"}
        )
        assert created.status_code == 201
        body = created.json()
        assert body["created"] and body["initial_admin_password"]
        assert ctx.login("empresa-c", "admin", body["initial_admin_password"]).status_code == 200

        again = ctx.client.post(
            "/api/v1/tenants", headers=sup, json={"slug": "empresa-c", "name": "Empresa C"}
        )
        assert again.status_code == 200
        assert again.json()["created"] is False and again.json()["initial_admin_password"] is None
        conflict = ctx.client.post(
            "/api/v1/tenants", headers=sup, json={"slug": "empresa-c", "name": "Otra"}
        )
        assert conflict.status_code == 409

    def test_a_provisioned_tenant_gets_its_own_dashboard(self, ctx: Ctx) -> None:
        sup = ctx.headers(None, "superadmin")
        body = ctx.client.post(
            "/api/v1/tenants", headers=sup, json={"slug": "empresa-c", "name": "Empresa C"}
        ).json()
        admin = ctx.headers("empresa-c", "admin") if False else None
        token = ctx.login("empresa-c", "admin", body["initial_admin_password"]).json()[
            "access_token"
        ]
        admin = {"Authorization": f"Bearer {token}"}
        c = ctx.client.get("/api/v1/capacity/dashboard", headers=admin)
        assert c.status_code == 200
        a = ctx.client.get("/api/v1/capacity/dashboard", headers=ctx.headers(A, "gerencia")).json()
        assert c.json()["totals"] != a["totals"]

    def test_invalid_slug_is_rejected_with_a_spanish_message(self, ctx: Ctx) -> None:
        sup = ctx.headers(None, "superadmin")
        response = ctx.client.post(
            "/api/v1/tenants", headers=sup, json={"slug": "Mala Empresa!", "name": "X Y"}
        )
        assert response.status_code == 422
        assert "identificador corto" in _error(response)["mensaje"]

    def test_unknown_tenant_returns_404(self, ctx: Ctx) -> None:
        sup = ctx.headers(None, "superadmin")
        assert ctx.client.post("/api/v1/tenants/no-existe/suspend", headers=sup).status_code == 404

    def test_extra_fields_in_provision_are_rejected(self, ctx: Ctx) -> None:
        sup = ctx.headers(None, "superadmin")
        response = ctx.client.post(
            "/api/v1/tenants",
            headers=sup,
            json={"slug": "empresa-d", "name": "Empresa D", "connection_string": "x"},
        )
        assert response.status_code == 422


class TestHardening:
    def test_security_headers_on_success_and_error_responses(self, ctx: Ctx) -> None:
        for response in (ctx.client.get("/api/v1/health"), ctx.client.get("/api/v1/me")):
            h = response.headers
            assert h["x-content-type-options"] == "nosniff"
            assert h["x-frame-options"] == "DENY"
            assert h["referrer-policy"] == "no-referrer"
            assert h["cache-control"] == "no-store"
            assert "frame-ancestors 'none'" in h["content-security-policy"]
            assert h["x-request-id"]

    def test_health_leaks_nothing(self, ctx: Ctx) -> None:
        assert ctx.client.get("/api/v1/health").json() == {"status": "ok"}

    def test_api_docs_are_only_available_in_the_local_environment(self, ctx: Ctx) -> None:
        # Entorno local (el de las pruebas): documentación habilitada para desarrollo.
        assert ctx.client.get("/api/v1/docs").status_code == 200
        # Cualquier otro entorno: apagada, con cookie Secure y HSTS.
        production = build_application(
            load_settings({"FLEETPLANNER_ENV": "production", "JWT_SIGNING_KEY": SIGNING_KEY}),
            clock=ctx.clock,
            hasher=FakeHasher(),
        )
        production_creds = seed_demo(production)
        client = TestClient(build_http_app(production), raise_server_exceptions=False)
        for path in ("/api/v1/docs", "/api/v1/openapi.json", "/docs", "/openapi.json"):
            assert client.get(path).status_code == 404
        health = client.get("/api/v1/health")
        assert "max-age" in health.headers["strict-transport-security"]
        login = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": A,
                "username": "gerencia",
                "password": password_of(production_creds, A, "gerencia"),
            },
        )
        assert login.status_code == 200
        assert "secure" in login.headers["set-cookie"].lower()

    def test_cors_is_a_strict_whitelist(self, ctx: Ctx) -> None:
        allowed = ctx.client.options(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
        )
        assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert allowed.headers.get("access-control-allow-credentials") == "true"
        denied = ctx.client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://sitio-malicioso.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in denied.headers

    def test_unexpected_errors_do_not_leak_details(
        self, ctx: Ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("secreto-interno-xyz C:\\ruta\\interna")

        monkeypatch.setattr(ctx.app.services.capacity_dashboard, "execute", boom)
        response = ctx.client.get("/api/v1/capacity/dashboard", headers=ctx.headers(A, "gerencia"))
        assert response.status_code == 500
        assert _error(response)["codigo"] == "ERROR_INTERNO"
        for leak in ("secreto-interno-xyz", "Traceback", "RuntimeError", "ruta"):
            assert leak not in response.text

    def test_oversized_bodies_are_refused(self, ctx: Ctx) -> None:
        response = ctx.client.post(
            "/api/v1/auth/login", json={"username": "a" * 70_000, "password": "x"}
        )
        assert response.status_code == 413

    def test_unknown_routes_and_methods_use_the_standard_error_shape(self, ctx: Ctx) -> None:
        missing = ctx.client.get("/api/v1/no-existe")
        assert missing.status_code == 404 and _error(missing)["codigo"] == "NO_ENCONTRADO"
        wrong = ctx.client.delete("/api/v1/health")
        assert wrong.status_code == 405 and _error(wrong)["codigo"] == "METODO_NO_PERMITIDO"

    def test_error_responses_are_in_spanish_with_a_request_id(self, ctx: Ctx) -> None:
        error = _error(ctx.client.get("/api/v1/me"))
        assert error["codigo"] == "AUTENTICACION_REQUERIDA"
        assert "iniciar sesión" in error["mensaje"]
        assert error["id_solicitud"] not in ("", "-")
