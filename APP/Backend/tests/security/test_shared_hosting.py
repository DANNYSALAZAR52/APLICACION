"""Demo compartida: contraseñas fijas por entorno, interfaz servida por la API y su CSP."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fleetplanner.bootstrap.application import build_http_app, seed_demo
from fleetplanner.bootstrap.settings import ConfigurationError, load_settings
from tenancy_helpers import SIGNING_KEY, A, make_app

warnings.filterwarnings("ignore", message=".*httpx.*")

BASE = {"JWT_SIGNING_KEY": SIGNING_KEY}
GOOD = "Contrasena-de-demo-2026"
OTHER = "Otra-contrasena-2026!"


class TestSettings:
    def test_defaults_are_local_and_closed(self) -> None:
        settings = load_settings(BASE)
        assert (settings.host, settings.port) == ("127.0.0.1", 8000)
        assert settings.frontend_dist is None
        assert settings.demo_password is None and settings.demo_superadmin_password is None

    def test_hosting_variables_are_read(self) -> None:
        settings = load_settings(
            {
                **BASE,
                "HOST": "0.0.0.0",  # noqa: S104 - el hospedaje enruta por su proxy
                "PORT": "8080",
                "FRONTEND_DIST": "/app/dist",
                "DEMO_PASSWORD": GOOD,
                "DEMO_SUPERADMIN_PASSWORD": OTHER,
            }
        )
        assert (settings.host, settings.port, settings.frontend_dist) == (
            "0.0.0.0",  # noqa: S104
            8080,
            "/app/dist",
        )
        assert settings.demo_password == GOOD

    def test_passwords_never_appear_in_repr(self) -> None:
        text = repr(load_settings({**BASE, "DEMO_PASSWORD": GOOD}))
        assert GOOD not in text and SIGNING_KEY not in text

    @pytest.mark.parametrize("password", ["corta", "12345678901"])
    def test_short_passwords_are_refused(self, password: str) -> None:
        with pytest.raises(ConfigurationError, match="al menos 12"):
            load_settings({**BASE, "DEMO_PASSWORD": password})

    def test_superadmin_password_must_differ(self) -> None:
        with pytest.raises(ConfigurationError, match="distinta"):
            load_settings({**BASE, "DEMO_PASSWORD": GOOD, "DEMO_SUPERADMIN_PASSWORD": GOOD})

    @pytest.mark.parametrize("port", ["abc", "0", "70000"])
    def test_invalid_port_is_refused(self, port: str) -> None:
        with pytest.raises(ConfigurationError, match="PORT"):
            load_settings({**BASE, "PORT": port})

    def test_production_still_requires_the_signing_key(self) -> None:
        with pytest.raises(ConfigurationError, match="JWT_SIGNING_KEY"):
            load_settings({"FLEETPLANNER_ENV": "production", "DEMO_PASSWORD": GOOD})


class TestFixedDemoPasswords:
    def test_every_demo_user_logs_in_with_the_shared_password(self) -> None:
        from fleetplanner.bootstrap.application import build_application
        from tenancy_helpers import FakeHasher

        app = build_application(load_settings(BASE), hasher=FakeHasher())
        credentials = seed_demo(app, GOOD, OTHER)
        client = TestClient(build_http_app(app), raise_server_exceptions=False)
        roles = {c.role.value for c in credentials}
        assert roles == {"management", "dispatcher", "driver", "tenant_admin", "super_admin"}
        for c in credentials:
            expected = OTHER if c.username == "superadmin" else GOOD
            assert c.password == expected
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "tenant_slug": None if c.username == "superadmin" else c.tenant,
                    "username": c.username,
                    "password": expected,
                },
            )
            assert response.status_code == 200, (c.tenant, c.username)

    def test_without_configuration_passwords_are_random_and_distinct(self) -> None:
        from fleetplanner.bootstrap.application import build_application
        from tenancy_helpers import FakeHasher

        app = build_application(load_settings(BASE), hasher=FakeHasher())
        passwords = [c.password for c in seed_demo(app)]
        assert len(set(passwords)) == len(passwords)
        assert all(len(p) >= 12 for p in passwords)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Demo</title><div id=root></div>")
    (root / "assets" / "app-abc123.js").write_text("console.log('ok')")
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secreto.txt").write_text("fuera de la carpeta")
    return root


@pytest.fixture
def served(dist: Path) -> TestClient:
    app, _, _ = make_app()
    return TestClient(build_http_app(app, frontend_dist=str(dist)), raise_server_exceptions=False)


class TestFrontendServing:
    def test_root_and_browser_routes_return_the_app(self, served: TestClient) -> None:
        for path in ("/", "/capacidad", "/torre-de-control", "/login"):
            response = served.get(path)
            assert response.status_code == 200
            assert "<title>Demo</title>" in response.text

    def test_hashed_assets_are_cacheable_but_the_page_is_not(self, served: TestClient) -> None:
        asset = served.get("/assets/app-abc123.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        assert served.get("/").headers["cache-control"] == "no-store"

    def test_static_files_in_the_root_are_served(self, served: TestClient) -> None:
        assert served.get("/favicon.svg").text == "<svg/>"

    def test_api_routes_are_never_shadowed(self, served: TestClient) -> None:
        assert served.get("/api/v1/health").json() == {"status": "ok"}
        unknown = served.get("/api/v1/no-existe")
        assert unknown.status_code == 404
        assert "<title>" not in unknown.text
        assert served.get("/api/v1/capacity/dashboard").status_code == 401

    @pytest.mark.parametrize(
        "path",
        [
            "/../secreto.txt",
            "/%2e%2e/secreto.txt",
            "/..%2fsecreto.txt",
            "/assets/../../secreto.txt",
        ],
    )
    def test_path_traversal_never_leaks_files_outside_the_folder(
        self, served: TestClient, path: str
    ) -> None:
        response = served.get(path)
        assert "fuera de la carpeta" not in response.text

    def test_csp_allows_only_what_the_app_needs_and_the_api_stays_closed(
        self, served: TestClient
    ) -> None:
        page = served.get("/").headers["content-security-policy"]
        assert "script-src 'self'" in page
        assert "https://tile.openstreetmap.org" in page
        assert "frame-ancestors 'none'" in page
        assert "unsafe-eval" not in page and "script-src 'self' 'unsafe-inline'" not in page
        api = served.get("/api/v1/health").headers["content-security-policy"]
        assert api == "default-src 'none'; frame-ancestors 'none'"

    def test_without_a_dist_folder_nothing_is_served(self) -> None:
        app, _, _ = make_app()
        client = TestClient(build_http_app(app), raise_server_exceptions=False)
        assert client.get("/").status_code == 404


class TestSameOriginSession:
    def test_login_and_refresh_work_from_the_served_origin(self, dist: Path) -> None:
        from fleetplanner.bootstrap.application import build_application
        from tenancy_helpers import FakeHasher

        app = build_application(load_settings(BASE), hasher=FakeHasher())
        seed_demo(app, GOOD, OTHER)
        client = TestClient(
            build_http_app(app, frontend_dist=str(dist)),
            base_url="https://demo.example.test",
            raise_server_exceptions=False,
        )
        origin = {"Origin": "https://demo.example.test"}
        login = client.post(
            "/api/v1/auth/login",
            headers=origin,
            json={"tenant_slug": A, "username": "gerencia", "password": GOOD},
        )
        assert login.status_code == 200
        refresh = client.post("/api/v1/auth/refresh", headers=origin)
        assert refresh.status_code == 200

    def test_a_foreign_origin_is_still_rejected(self, dist: Path) -> None:
        app, _, _ = make_app()
        client = TestClient(
            build_http_app(app, frontend_dist=str(dist)), raise_server_exceptions=False
        )
        response = client.post(
            "/api/v1/auth/refresh", headers={"Origin": "https://evil.example.test"}
        )
        assert response.status_code == 403
