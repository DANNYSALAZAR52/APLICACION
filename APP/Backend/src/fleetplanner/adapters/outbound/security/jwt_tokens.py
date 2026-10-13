"""Tokens de acceso JWT firmados (`TokenServicePort`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from fleetplanner.application.dto.security import AccessToken, TokenClaims
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.domain.shared.errors import AuthenticationError
from fleetplanner.domain.tenancy.models import Role

ISSUER = "fleetplanner"
_ALGORITHM = "HS256"
_MIN_KEY_BYTES = 32


class JwtTokenService:
    """Access tokens de vida corta con el tenant y el rol como claims firmados.

    * Algoritmo fijo (no se acepta el que declare el token), con issuer y claims obligatorios.
    * La expiración se valida con el reloj inyectado, no con el del sistema.
    * El token solo prueba autenticidad: `AuthenticateRequest` revalida usuario, rol y tenant.
    """

    def __init__(self, signing_key: str, clock: ClockPort, ttl: timedelta = timedelta(minutes=15)):
        if len(signing_key.encode()) < _MIN_KEY_BYTES:
            raise ValueError(
                f"La clave de firma debe tener al menos {_MIN_KEY_BYTES} bytes; "
                "configure JWT_SIGNING_KEY."
            )
        self._key = signing_key
        self._clock = clock
        self._ttl = ttl

    def issue_access_token(self, user_id: str, tenant_id: str | None, role: Role) -> AccessToken:
        issued = self._clock.now()
        expires = issued + self._ttl
        payload = {
            "iss": ISSUER,
            "sub": user_id,
            "tid": tenant_id,
            "role": role.value,
            "jti": uuid.uuid4().hex,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return AccessToken(jwt.encode(payload, self._key, algorithm=_ALGORITHM), expires)

    def verify_access_token(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._key,
                algorithms=[_ALGORITHM],
                issuer=ISSUER,
                options={"require": ["exp", "iat", "sub", "jti", "iss"], "verify_exp": False},
            )
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
            if expires_at <= self._clock.now():
                raise AuthenticationError("La sesión expiró.")
            tid = payload.get("tid")
            return TokenClaims(
                user_id=str(payload["sub"]),
                tenant_id=str(tid) if tid else None,
                role=Role(payload["role"]),
                jti=str(payload["jti"]),
                expires_at=expires_at,
            )
        except AuthenticationError:
            raise
        except (jwt.PyJWTError, KeyError, ValueError, TypeError) as error:
            raise AuthenticationError("La sesión no es válida.") from error
