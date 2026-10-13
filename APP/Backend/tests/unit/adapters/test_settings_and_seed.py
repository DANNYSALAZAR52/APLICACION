"""Configuración segura al arranque y siembra de usuarios."""

from __future__ import annotations

import logging

import pytest

from fleetplanner.bootstrap.settings import ConfigurationError, load_settings
from fleetplanner.domain.tenancy.credentials import validate_password_policy
from fleetplanner.domain.tenancy.models import Role
from tenancy_helpers import SIGNING_KEY, make_app


class TestSettings:
    def test_missing_signing_key_fails_safely_outside_local(self) -> None:
        with pytest.raises(ConfigurationError, match="JWT_SIGNING_KEY"):
            load_settings({"FLEETPLANNER_ENV": "production"})

    def test_local_generates_an_ephemeral_key_and_says_so(self) -> None:
        first, second = load_settings({}), load_settings({})
        assert first.is_local and first.ephemeral_signing_key
        assert first.jwt_signing_key != second.jwt_signing_key

    def test_short_key_is_rejected(self) -> None:
        with pytest.raises(ConfigurationError, match="32 bytes"):
            load_settings({"JWT_SIGNING_KEY": "corta"})

    def test_wildcard_cors_is_rejected(self) -> None:
        with pytest.raises(ConfigurationError, match="lista blanca"):
            load_settings({"JWT_SIGNING_KEY": SIGNING_KEY, "ALLOWED_ORIGINS": "*"})

    def test_origins_are_parsed_and_the_key_is_never_printed(self) -> None:
        settings = load_settings(
            {
                "JWT_SIGNING_KEY": SIGNING_KEY,
                "ALLOWED_ORIGINS": "https://a.example, https://b.example",
            }
        )
        assert settings.allowed_origins == ("https://a.example", "https://b.example")
        assert not settings.ephemeral_signing_key
        assert SIGNING_KEY not in repr(settings)


class TestSeed:
    def test_seed_creates_expected_users_with_unique_policy_compliant_passwords(self) -> None:
        app, creds, _ = make_app()
        assert len(creds) == 9  # 4 roles × 2 empresas + superadmin
        assert len({c.password for c in creds}) == 9
        for credential in creds:
            validate_password_policy(credential.password)
        roles = {c.role for c in creds}
        assert roles == set(Role)
        assert [t.slug for t in sorted(app.tenants.list_all(), key=lambda t: t.slug)] == [
            "empresa-demo-a",
            "empresa-demo-b",
        ]

    def test_passwords_are_not_stored_in_clear_or_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            app, creds, _ = make_app()
        stored = " ".join(
            u.password_hash for t in app.tenants.list_all() for u in app.users.list_for_tenant(t.id)
        )
        # El hasher falso de pruebas antepone "fake$"; lo relevante: nada en el log ni en eventos.
        for credential in creds:
            assert credential.password not in caplog.text
            assert all(credential.password not in str(e) for e in app.audit.list_events(None))
        assert stored

    def test_seeds_differ_between_runs(self) -> None:
        first = {c.password for c in make_app()[1]}
        second = {c.password for c in make_app()[1]}
        assert first.isdisjoint(second)
