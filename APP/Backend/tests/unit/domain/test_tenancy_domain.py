"""Dominio de tenancy: RBAC, invariantes, política de contraseñas y bloqueo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fleetplanner.domain.shared.errors import InvalidValueError, PermissionDeniedError
from fleetplanner.domain.tenancy.access_policy import AccessPolicy, Permission
from fleetplanner.domain.tenancy.credentials import (
    LockoutPolicy,
    generate_password,
    validate_password_policy,
)
from fleetplanner.domain.tenancy.models import (
    Principal,
    Role,
    Tenant,
    TenantId,
    TenantStatus,
    User,
)

NOW = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)


def _principal(role: Role) -> Principal:
    tenant = None if role is Role.SUPER_ADMIN else TenantId("t-1")
    return Principal("u1", "user", role, tenant, None if tenant is None else "demo")


class TestAccessPolicy:
    @pytest.mark.parametrize(
        ("role", "allowed"),
        [
            (Role.MANAGEMENT, {Permission.CAPACITY_READ, Permission.INDICATORS_READ}),
            (Role.DISPATCHER, {Permission.ROUTING_EVENTS, Permission.ROUTING_READ}),
            (Role.DRIVER, {Permission.DRIVER_ROUTE}),
            (Role.TENANT_ADMIN, {Permission.MASTER_DATA_MANAGE, Permission.AUDIT_READ}),
            (Role.SUPER_ADMIN, {Permission.TENANTS_MANAGE, Permission.AUDIT_READ}),
        ],
    )
    def test_each_role_has_its_grants(self, role: Role, allowed: set[Permission]) -> None:
        for permission in allowed:
            assert AccessPolicy.can(_principal(role), permission)

    @pytest.mark.parametrize(
        ("role", "denied"),
        [
            (Role.MANAGEMENT, {Permission.ROUTING_EVENTS, Permission.TENANTS_MANAGE}),
            (Role.DISPATCHER, {Permission.CAPACITY_READ, Permission.MASTER_DATA_MANAGE}),
            (
                Role.DRIVER,
                {Permission.CAPACITY_READ, Permission.ROUTING_READ, Permission.AUDIT_READ},
            ),
            (Role.TENANT_ADMIN, {Permission.TENANTS_MANAGE, Permission.ROUTING_EVENTS}),
            (Role.SUPER_ADMIN, {Permission.CAPACITY_READ, Permission.ROUTING_EVENTS}),
        ],
    )
    def test_everything_else_is_denied(self, role: Role, denied: set[Permission]) -> None:
        for permission in denied:
            assert not AccessPolicy.can(_principal(role), permission)
            with pytest.raises(PermissionDeniedError):
                AccessPolicy.require(_principal(role), permission)

    def test_only_super_admin_can_manage_tenants(self) -> None:
        holders = [r for r in Role if Permission.TENANTS_MANAGE in AccessPolicy.permissions_of(r)]
        assert holders == [Role.SUPER_ADMIN]

    def test_every_permission_is_granted_to_someone(self) -> None:
        granted = {p for r in Role for p in AccessPolicy.permissions_of(r)}
        assert Permission.MASTER_DATA_MANAGE in granted


class TestTenantAndUser:
    @pytest.mark.parametrize("slug", ["Empresa A", "-a", "a_b", "", "x" * 41, "ñandú"])
    def test_invalid_slug_rejected(self, slug: str) -> None:
        with pytest.raises(InvalidValueError, match="identificador corto"):
            Tenant(TenantId("t"), slug, "Nombre", TenantStatus.ACTIVE, NOW)

    def test_suspend_and_reactivate_return_new_objects(self) -> None:
        tenant = Tenant(TenantId("t"), "demo", "Demo", TenantStatus.ACTIVE, NOW)
        suspended = tenant.suspended()
        assert tenant.is_active and not suspended.is_active
        assert suspended.reactivated().is_active

    def test_super_admin_cannot_belong_to_a_tenant(self) -> None:
        with pytest.raises(InvalidValueError):
            User("u", TenantId("t"), "root", "Root", Role.SUPER_ADMIN, "h")

    def test_regular_user_requires_a_tenant(self) -> None:
        with pytest.raises(InvalidValueError):
            User("u", None, "ana", "Ana", Role.DRIVER, "h")


class TestPasswords:
    @pytest.mark.parametrize("bad", ["corta1", "x" * 129, "soloLetrasSinNumero", "123456789012345"])
    def test_weak_passwords_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidValueError):
            validate_password_policy(bad)

    def test_valid_password_accepted(self) -> None:
        validate_password_policy("ClaveSegura2026!")

    def test_generated_passwords_meet_policy_and_differ(self) -> None:
        generated = {generate_password() for _ in range(50)}
        assert len(generated) == 50
        for password in generated:
            validate_password_policy(password)


class TestLockout:
    def test_no_lock_below_threshold(self) -> None:
        policy = LockoutPolicy(threshold=5)
        assert policy.locked_until_after_failure(4, NOW) is None

    def test_lock_doubles_and_is_capped(self) -> None:
        policy = LockoutPolicy(
            threshold=5, base=timedelta(seconds=30), max_lock=timedelta(minutes=15)
        )
        assert policy.locked_until_after_failure(5, NOW) == NOW + timedelta(seconds=30)
        assert policy.locked_until_after_failure(6, NOW) == NOW + timedelta(seconds=60)
        assert policy.locked_until_after_failure(7, NOW) == NOW + timedelta(seconds=120)
        assert policy.locked_until_after_failure(60, NOW) == NOW + timedelta(minutes=15)

    def test_is_locked(self) -> None:
        until = NOW + timedelta(seconds=10)
        assert LockoutPolicy.is_locked(until, NOW)
        assert not LockoutPolicy.is_locked(until, until)
        assert not LockoutPolicy.is_locked(None, NOW)

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            LockoutPolicy(threshold=0)
