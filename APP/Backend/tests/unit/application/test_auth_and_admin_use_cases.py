"""Casos de uso de autenticación y administración, con adaptadores en memoria y reloj fijo."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from fleetplanner.application.dto.security import AuditOutcome, LoginCommand
from fleetplanner.application.use_cases.auth import GENERIC_LOGIN_ERROR
from fleetplanner.domain.shared.errors import (
    AuthenticationError,
    ConflictError,
    InvalidValueError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    TenantSuspendedError,
)
from fleetplanner.domain.tenancy.models import Role, TenantStatus
from tenancy_helpers import A, B, make_app, password_of


@pytest.fixture
def ctx():  # type: ignore[no-untyped-def]
    return make_app()


def _login(app, slug, username, password, client="1.1.1.1"):  # type: ignore[no-untyped-def]
    return app.services.login.execute(LoginCommand(slug, username, password, client))


def _super(app, creds):  # type: ignore[no-untyped-def]
    session = _login(app, None, "superadmin", password_of(creds, "(sin empresa)", "superadmin"))
    return session.principal


class TestLogin:
    def test_success_returns_session_and_audits(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        session = _login(app, A, "gerencia", password_of(creds, A, "gerencia"))
        assert session.principal.role is Role.MANAGEMENT
        assert session.principal.tenant_slug == A
        assert session.principal.tenant_name == "Empresa Demo A"
        assert session.access.token and session.refresh.token
        events = app.audit.list_events(None)
        assert events[0].action == "auth.login" and events[0].outcome is AuditOutcome.SUCCESS

    def test_username_is_case_insensitive_but_password_is_not(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        password = password_of(creds, A, "gerencia")
        assert _login(app, A, "GERENCIA", password).principal.username == "gerencia"
        with pytest.raises(AuthenticationError):
            _login(app, A, "gerencia", password.upper())

    def test_every_failure_mode_gives_the_same_message(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        good = password_of(creds, A, "gerencia")
        attempts = [
            (A, "gerencia", "mala-clave-2026"),  # contraseña errónea
            (A, "no-existe", good),  # usuario inexistente
            ("empresa-fantasma", "gerencia", good),  # empresa inexistente
            (B, "gerencia", good),  # usuario de otra empresa
            (None, "gerencia", good),  # sin empresa: solo superadmin
        ]
        messages = set()
        for slug, user, password in attempts:
            with pytest.raises(AuthenticationError) as caught:
                _login(app, slug, user, password, client=f"ip-{user}-{slug}")
            messages.add(str(caught.value))
        assert messages == {GENERIC_LOGIN_ERROR}

    def test_progressive_lockout_blocks_even_the_right_password(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, clock = ctx
        good = password_of(creds, A, "gerencia")
        for i in range(5):
            with pytest.raises(AuthenticationError):
                _login(app, A, "gerencia", "mala-clave-2026", client=f"ip{i}")
        with pytest.raises(AuthenticationError):
            _login(app, A, "gerencia", good, client="ip-x")  # bloqueada: 30 s
        clock.advance(timedelta(seconds=31))
        assert _login(app, A, "gerencia", good, client="ip-y").principal.username == "gerencia"
        # el éxito reinicia el contador
        user = app.users.find_by_login(app.tenants.get_by_slug(A).id, "gerencia")  # type: ignore[union-attr]
        assert user is not None and user.failed_attempts == 0

    def test_rate_limit_per_account(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        with pytest.raises(RateLimitedError):
            for i in range(12):
                try:
                    _login(app, A, "despachador", "mala-clave-2026", client=f"ip{i}")
                except AuthenticationError:
                    continue

    def test_rate_limit_per_origin(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, _, _ = ctx
        with pytest.raises(RateLimitedError):
            for i in range(60):
                try:
                    _login(app, A, f"usuario-{i}", "mala-clave-2026", client="misma-ip")
                except AuthenticationError:
                    continue

    def test_suspended_tenant_is_only_revealed_after_a_correct_password(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        sup = _super(app, creds)
        app.services.set_tenant_status.execute(sup, A, TenantStatus.SUSPENDED)
        with pytest.raises(AuthenticationError):
            _login(app, A, "gerencia", "mala-clave-2026", client="i1")
        with pytest.raises(TenantSuspendedError):
            _login(app, A, "gerencia", password_of(creds, A, "gerencia"), client="i2")
        # la otra empresa no se ve afectada
        assert (
            _login(app, B, "gerencia", password_of(creds, B, "gerencia")).principal.tenant_slug == B
        )

    def test_super_admin_logs_in_without_tenant(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        principal = _super(app, creds)
        assert principal.role is Role.SUPER_ADMIN and principal.tenant_id is None

    def test_inactive_user_cannot_login(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        tenant = app.tenants.get_by_slug(A)
        assert tenant is not None
        user = app.users.find_by_login(tenant.id, "conductor")
        assert user is not None
        app.users.save(replace(user, active=False))
        with pytest.raises(AuthenticationError):
            _login(app, A, "conductor", password_of(creds, A, "conductor"))

    def test_password_is_hidden_in_command_repr(self) -> None:
        assert "secreta" not in repr(LoginCommand(A, "x", "secreta-2026"))


class TestAuthenticateRequest:
    def _token(self, ctx, username="gerencia", slug=A):  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        return _login(app, slug, username, password_of(creds, slug, username)).access.token

    def test_valid_token_gives_a_principal_from_stored_data(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, _, _ = ctx
        principal = app.services.authenticate.execute(self._token(ctx))
        assert principal.tenant_slug == A and principal.role is Role.MANAGEMENT

    def test_role_change_in_store_invalidates_old_tokens(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, _, _ = ctx
        token = self._token(ctx)
        tenant = app.tenants.get_by_slug(A)
        assert tenant is not None
        user = app.users.find_by_login(tenant.id, "gerencia")
        assert user is not None
        app.users.save(replace(user, role=Role.DRIVER))
        with pytest.raises(AuthenticationError):
            app.services.authenticate.execute(token)

    def test_deactivated_user_is_rejected_immediately(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, _, _ = ctx
        token = self._token(ctx)
        tenant = app.tenants.get_by_slug(A)
        assert tenant is not None
        user = app.users.find_by_login(tenant.id, "gerencia")
        assert user is not None
        app.users.save(replace(user, active=False))
        with pytest.raises(AuthenticationError):
            app.services.authenticate.execute(token)

    def test_suspension_blocks_existing_tokens(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        token = self._token(ctx)
        app.services.set_tenant_status.execute(_super(app, creds), A, TenantStatus.SUSPENDED)
        with pytest.raises(TenantSuspendedError):
            app.services.authenticate.execute(token)
        app.services.set_tenant_status.execute(_super(app, creds), A, TenantStatus.ACTIVE)
        assert app.services.authenticate.execute(token).tenant_slug == A

    def test_garbage_is_rejected(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, _, _ = ctx
        with pytest.raises(AuthenticationError):
            app.services.authenticate.execute("basura")


class TestSessions:
    def test_refresh_rotates_and_old_token_dies(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        first = _login(app, A, "gerencia", password_of(creds, A, "gerencia"))
        second = app.services.refresh.execute(first.refresh.token)
        assert second.refresh.token != first.refresh.token
        with pytest.raises(AuthenticationError):
            app.services.refresh.execute(first.refresh.token)
        with pytest.raises(AuthenticationError):  # la familia entera quedó revocada
            app.services.refresh.execute(second.refresh.token)

    def test_logout_revokes_access_and_refresh(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        session = _login(app, A, "gerencia", password_of(creds, A, "gerencia"))
        app.services.logout.execute(session.access.token, session.refresh.token)
        with pytest.raises(AuthenticationError):
            app.services.authenticate.execute(session.access.token)
        with pytest.raises(AuthenticationError):
            app.services.refresh.execute(session.refresh.token)

    def test_refresh_fails_for_suspended_tenant(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        session = _login(app, A, "gerencia", password_of(creds, A, "gerencia"))
        app.services.set_tenant_status.execute(_super(app, creds), A, TenantStatus.SUSPENDED)
        with pytest.raises(AuthenticationError):
            app.services.refresh.execute(session.refresh.token)


class TestTenantAdministration:
    def test_only_super_admin_can_use_tenant_administration(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        for username in ("gerencia", "despachador", "conductor", "admin"):
            principal = _login(app, A, username, password_of(creds, A, username)).principal
            with pytest.raises(PermissionDeniedError):
                app.services.list_tenants.execute(principal)
            with pytest.raises(PermissionDeniedError):
                app.services.provision_tenant.execute(principal, "nueva", "Nueva")
            with pytest.raises(PermissionDeniedError):
                app.services.set_tenant_status.execute(principal, B, TenantStatus.SUSPENDED)

    def test_provision_creates_tenant_and_a_working_admin(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        result = app.services.provision_tenant.execute(
            _super(app, creds), "empresa-nueva", "Empresa Nueva"
        )
        assert result.created and result.admin_username == "admin"
        assert result.initial_admin_password
        session = _login(app, "empresa-nueva", "admin", result.initial_admin_password)
        assert session.principal.role is Role.TENANT_ADMIN
        assert "Argon" not in repr(result) and result.initial_admin_password not in repr(result)

    def test_provision_is_idempotent_and_detects_conflicts(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        sup = _super(app, creds)
        first = app.services.provision_tenant.execute(sup, "empresa-nueva", "Empresa Nueva")
        again = app.services.provision_tenant.execute(sup, "empresa-nueva", "Empresa Nueva")
        assert again.created is False and again.initial_admin_password is None
        assert again.tenant.id == first.tenant.id
        assert len([t for t in app.tenants.list_all() if t.slug == "empresa-nueva"]) == 1
        with pytest.raises(ConflictError):
            app.services.provision_tenant.execute(sup, "empresa-nueva", "Otro nombre")

    def test_invalid_provision_leaves_no_partial_state(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        tenants_before = len(app.tenants.list_all())
        users_before = sum(len(app.users.list_for_tenant(t.id)) for t in app.tenants.list_all())
        with pytest.raises(InvalidValueError):
            app.services.provision_tenant.execute(_super(app, creds), "Mala Empresa!", "X")
        assert len(app.tenants.list_all()) == tenants_before
        assert (
            sum(len(app.users.list_for_tenant(t.id)) for t in app.tenants.list_all())
            == users_before
        )

    def test_list_tenants_is_sorted_and_counts_users(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        summaries = app.services.list_tenants.execute(_super(app, creds))
        assert [s.tenant.slug for s in summaries] == [A, B]
        assert {s.user_count for s in summaries} == {4}

    def test_suspending_revokes_sessions_and_unknown_tenant_is_not_found(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        sup = _super(app, creds)
        session = _login(app, A, "gerencia", password_of(creds, A, "gerencia"))
        app.services.set_tenant_status.execute(sup, A, TenantStatus.SUSPENDED)
        with pytest.raises(AuthenticationError):
            app.services.refresh.execute(session.refresh.token)
        with pytest.raises(NotFoundError):
            app.services.set_tenant_status.execute(sup, "no-existe", TenantStatus.SUSPENDED)


class TestAuditAccess:
    def test_tenant_admin_only_sees_own_tenant_super_admin_sees_all(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        _login(app, A, "gerencia", password_of(creds, A, "gerencia"))
        _login(app, B, "gerencia", password_of(creds, B, "gerencia"))
        admin_a = _login(app, A, "admin", password_of(creds, A, "admin")).principal
        seen = app.services.list_audit.execute(admin_a)
        assert seen and {e.tenant_id for e in seen} == {str(admin_a.tenant_id)}
        everything = app.services.list_audit.execute(_super(app, creds))
        tenants_seen = {e.tenant_id for e in everything}
        assert str(admin_a.tenant_id) in tenants_seen
        assert len(tenants_seen) >= 3  # empresa A, empresa B y el superadministrador (None)
        assert len(everything) > len(seen)

    @pytest.mark.parametrize("username", ["gerencia", "despachador", "conductor"])
    def test_other_roles_cannot_read_the_audit_log(self, ctx, username: str) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        principal = _login(app, A, username, password_of(creds, A, username)).principal
        with pytest.raises(PermissionDeniedError):
            app.services.list_audit.execute(principal)


class TestCapacityAccess:
    def test_management_gets_data_of_own_tenant_only(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        a = _login(app, A, "gerencia", password_of(creds, A, "gerencia")).principal
        b = _login(app, B, "gerencia", password_of(creds, B, "gerencia")).principal
        dash_a = app.services.capacity_dashboard.execute(a)
        dash_b = app.services.capacity_dashboard.execute(b)
        assert (
            dash_a.balance.requirement.total_required != dash_b.balance.requirement.total_required
        )
        assert (
            dash_a.balance.requirement.current_by_type != dash_b.balance.requirement.current_by_type
        )
        # repetir da lo mismo (determinista) y no se mezcla con el otro tenant
        again = app.services.capacity_dashboard.execute(a)
        assert (
            again.balance.requirement.required_by_type
            == dash_a.balance.requirement.required_by_type
        )

    @pytest.mark.parametrize("username", ["despachador", "conductor"])
    def test_roles_without_permission_are_denied_and_audited(self, ctx, username: str) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        principal = _login(app, A, username, password_of(creds, A, username)).principal
        with pytest.raises(PermissionDeniedError):
            app.services.capacity_dashboard.execute(principal)
        last = app.audit.list_events(None)[0]
        assert last.action == "capacity.dashboard.view" and last.outcome is AuditOutcome.DENIED

    def test_super_admin_has_no_capacity_access(self, ctx) -> None:  # type: ignore[no-untyped-def]
        app, creds, _ = ctx
        with pytest.raises(PermissionDeniedError):
            app.services.capacity_dashboard.execute(_super(app, creds))
