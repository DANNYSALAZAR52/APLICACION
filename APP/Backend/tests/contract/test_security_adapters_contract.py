"""Contratos de los adaptadores de seguridad, sesiones, auditoría y límite de tasa."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from fleetplanner.adapters.outbound.clock import FixedClock
from fleetplanner.adapters.outbound.persistence_memory import (
    InMemoryAuditLog,
    InMemoryRateLimiter,
    InMemoryRefreshTokenStore,
)
from fleetplanner.adapters.outbound.security import Argon2PasswordHasher, JwtTokenService
from fleetplanner.application.dto.security import AuditEvent, AuditOutcome
from fleetplanner.domain.shared.errors import AuthenticationError
from fleetplanner.domain.tenancy.models import Role
from tenancy_helpers import NOW, SIGNING_KEY


class TestArgon2Hasher:
    def test_uses_argon2id_and_verifies(self) -> None:
        hasher = Argon2PasswordHasher()
        digest = hasher.hash("ClaveSegura2026!")
        assert digest.startswith("$argon2id$")
        assert "ClaveSegura2026!" not in digest
        assert hasher.verify(digest, "ClaveSegura2026!")
        assert not hasher.verify(digest, "otra-clave-2026")

    def test_same_password_gives_different_hashes(self) -> None:
        hasher = Argon2PasswordHasher()
        assert hasher.hash("ClaveSegura2026!") != hasher.hash("ClaveSegura2026!")

    def test_malformed_hash_is_a_failed_verification_not_a_crash(self) -> None:
        assert not Argon2PasswordHasher().verify("no-es-un-hash", "x")

    def test_dummy_verification_never_raises(self) -> None:
        Argon2PasswordHasher().verify_dummy("cualquier-cosa")


class TestJwtTokenService:
    @staticmethod
    def _service(clock: FixedClock | None = None) -> tuple[JwtTokenService, FixedClock]:
        clock = clock or FixedClock(NOW)
        return JwtTokenService(SIGNING_KEY, clock), clock

    def test_roundtrip_preserves_signed_claims(self) -> None:
        service, _ = self._service()
        token = service.issue_access_token("u1", "t-1", Role.MANAGEMENT)
        claims = service.verify_access_token(token.token)
        assert (claims.user_id, claims.tenant_id, claims.role) == ("u1", "t-1", Role.MANAGEMENT)
        assert claims.expires_at == token.expires_at == NOW + timedelta(minutes=15)

    def test_super_admin_token_has_no_tenant(self) -> None:
        service, _ = self._service()
        token = service.issue_access_token("u1", None, Role.SUPER_ADMIN)
        assert service.verify_access_token(token.token).tenant_id is None

    def test_token_expires_by_the_injected_clock(self) -> None:
        service, clock = self._service()
        token = service.issue_access_token("u1", "t-1", Role.DRIVER).token
        clock.advance(timedelta(minutes=14))
        service.verify_access_token(token)
        clock.advance(timedelta(minutes=2))
        with pytest.raises(AuthenticationError):
            service.verify_access_token(token)

    def test_each_token_has_a_unique_id(self) -> None:
        service, _ = self._service()
        ids = {
            service.verify_access_token(service.issue_access_token("u", "t", Role.DRIVER).token).jti
            for _ in range(20)
        }
        assert len(ids) == 20

    def test_token_signed_with_another_key_is_rejected(self) -> None:
        service, _ = self._service()
        forged = JwtTokenService("otra-clave-distinta-de-al-menos-32-bytes!!", FixedClock(NOW))
        token = forged.issue_access_token("u1", "t-1", Role.MANAGEMENT).token
        with pytest.raises(AuthenticationError):
            service.verify_access_token(token)

    def test_tampered_payload_is_rejected(self) -> None:
        service, _ = self._service()
        head, body, sig = service.issue_access_token("u1", "t-1", Role.DRIVER).token.split(".")
        other = service.issue_access_token("u2", "t-2", Role.SUPER_ADMIN).token.split(".")[1]
        for broken in (f"{head}.{other}.{sig}", f"{head}.{body}.{sig[:-2]}AA", "no.es.jwt", ""):
            with pytest.raises(AuthenticationError):
                service.verify_access_token(broken)

    def test_alg_none_and_other_algorithms_are_rejected(self) -> None:
        service, _ = self._service()
        now = int(NOW.timestamp())
        payload = {
            "iss": "fleetplanner",
            "sub": "u1",
            "tid": "t-1",
            "role": "management",
            "jti": "x",
            "iat": now,
            "exp": now + 600,
        }
        unsigned = jwt.encode(payload, key="", algorithm="none")
        hs512 = jwt.encode(payload, SIGNING_KEY, algorithm="HS512")
        for token in (unsigned, hs512):
            with pytest.raises(AuthenticationError):
                service.verify_access_token(token)

    @pytest.mark.parametrize("missing", ["jti", "sub", "exp", "iss", "role"])
    def test_required_claims_are_enforced(self, missing: str) -> None:
        service, _ = self._service()
        now = int(NOW.timestamp())
        payload = {
            "iss": "fleetplanner",
            "sub": "u1",
            "tid": "t-1",
            "role": "management",
            "jti": "x",
            "iat": now,
            "exp": now + 600,
        }
        del payload[missing]
        with pytest.raises(AuthenticationError):
            service.verify_access_token(jwt.encode(payload, SIGNING_KEY, algorithm="HS256"))

    def test_wrong_issuer_and_unknown_role_are_rejected(self) -> None:
        service, _ = self._service()
        now = int(NOW.timestamp())
        base = {
            "iss": "fleetplanner",
            "sub": "u1",
            "tid": None,
            "role": "management",
            "jti": "x",
            "iat": now,
            "exp": now + 600,
        }
        for changed in ({"iss": "otro"}, {"role": "root"}):
            token = jwt.encode({**base, **changed}, SIGNING_KEY, algorithm="HS256")
            with pytest.raises(AuthenticationError):
                service.verify_access_token(token)

    def test_short_signing_key_is_refused(self) -> None:
        with pytest.raises(ValueError, match="al menos 32 bytes"):
            JwtTokenService("corta", FixedClock(NOW))


class TestRefreshTokenStore:
    @staticmethod
    def _store() -> tuple[InMemoryRefreshTokenStore, FixedClock]:
        clock = FixedClock(NOW)
        return InMemoryRefreshTokenStore(clock, ttl=timedelta(hours=1)), clock

    def test_rotation_returns_same_user_and_a_new_token(self) -> None:
        store, _ = self._store()
        first = store.issue("u1")
        user_id, second = store.rotate(first.token)
        assert user_id == "u1"
        assert second.token != first.token
        assert store.rotate(second.token)[0] == "u1"

    def test_reusing_a_rotated_token_revokes_the_whole_family(self) -> None:
        store, _ = self._store()
        first = store.issue("u1")
        _, second = store.rotate(first.token)
        with pytest.raises(AuthenticationError):
            store.rotate(first.token)  # reutilización: se asume robo
        with pytest.raises(AuthenticationError):
            store.rotate(second.token)  # el token legítimo también queda revocado

    def test_unknown_and_expired_tokens_are_rejected(self) -> None:
        store, clock = self._store()
        with pytest.raises(AuthenticationError):
            store.rotate("desconocido")
        grant = store.issue("u1")
        clock.advance(timedelta(hours=1, seconds=1))
        with pytest.raises(AuthenticationError):
            store.rotate(grant.token)

    def test_revoke_and_revoke_all(self) -> None:
        store, _ = self._store()
        a, b, other = store.issue("u1"), store.issue("u1"), store.issue("u2")
        store.revoke(a.token)
        with pytest.raises(AuthenticationError):
            store.rotate(a.token)
        store.revoke_all_for_user("u1")
        with pytest.raises(AuthenticationError):
            store.rotate(b.token)
        assert store.rotate(other.token)[0] == "u2"

    def test_access_token_revocation_lasts_until_it_expires(self) -> None:
        store, clock = self._store()
        store.revoke_access("jti-1", NOW + timedelta(minutes=15))
        assert store.is_access_revoked("jti-1")
        assert not store.is_access_revoked("jti-2")
        clock.advance(timedelta(minutes=16))
        assert not store.is_access_revoked("jti-1")


class TestRateLimiter:
    def test_blocks_after_limit_and_recovers_after_window(self) -> None:
        clock = FixedClock(NOW)
        limiter = InMemoryRateLimiter(clock)
        assert [limiter.allow("k", 3, 60) for _ in range(4)] == [True, True, True, False]
        assert limiter.allow("otra", 3, 60)  # claves independientes
        clock.advance(timedelta(seconds=61))
        assert limiter.allow("k", 3, 60)


class TestAuditLog:
    @staticmethod
    def _event(tenant: str | None, action: str) -> AuditEvent:
        return AuditEvent(NOW, action, AuditOutcome.SUCCESS, tenant, "u", "user")

    def test_filters_by_tenant_and_returns_newest_first(self) -> None:
        log = InMemoryAuditLog()
        for tenant, action in [("a", "1"), ("b", "2"), ("a", "3")]:
            log.record(self._event(tenant, action))
        assert [e.action for e in log.list_events("a")] == ["3", "1"]
        assert [e.action for e in log.list_events(None)] == ["3", "2", "1"]
        assert len(log.list_events(None, limit=2)) == 2

    def test_log_is_bounded(self) -> None:
        log = InMemoryAuditLog(capacity=3)
        for i in range(10):
            log.record(self._event("a", str(i)))
        assert [e.action for e in log.list_events(None)] == ["9", "8", "7"]
