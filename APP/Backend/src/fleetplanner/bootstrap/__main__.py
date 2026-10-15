"""Punto de entrada de la demo.

* ``python -m fleetplanner.bootstrap capacity`` — informe de capacidad en consola.
* ``python -m fleetplanner.bootstrap serve [--host 127.0.0.1] [--port 8000]`` — API HTTP con datos
  sembrados. Con ``FRONTEND_DIST`` también sirve la interfaz compilada (un solo proceso).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fleetplanner.adapters.inbound.cli import run_capacity_cli
from fleetplanner.adapters.outbound.demo_data import DEMO_LABEL
from fleetplanner.bootstrap.application import (
    SeedCredential,
    build_application,
    build_http_app,
    seed_demo,
)
from fleetplanner.bootstrap.container import build_capacity_container
from fleetplanner.bootstrap.settings import ConfigurationError, load_settings


def _print_credentials(
    credentials: list[SeedCredential], ephemeral_key: bool, fixed: bool = False
) -> None:
    print("=" * 78)
    if fixed:
        print(
            f"  {DEMO_LABEL} — usuarios sembrados (contraseñas definidas por variables de entorno)"
        )
    else:
        print(f"  {DEMO_LABEL} — usuarios sembrados (contraseñas aleatorias, SE MUESTRAN UNA VEZ)")
    print("=" * 78)
    print(f"  {'empresa':<18}{'usuario':<14}{'rol':<14}contraseña")
    for c in credentials:
        shown = "(la definida en el entorno)" if fixed else c.password
        print(f"  {c.tenant:<18}{c.username:<14}{c.role.value:<14}{shown}")
    print("-" * 78)
    if not fixed:
        print("  Anótelas ahora: no se guardan en disco ni se vuelven a mostrar.")
    if ephemeral_key:
        print("  Clave de firma efímera (solo local): las sesiones caducan al reiniciar.")
    print("=" * 78, flush=True)


def _serve(host: str | None, port: int | None) -> int:
    import uvicorn

    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"Configuración inválida: {error}", file=sys.stderr)
        return 1
    application = build_application(settings)
    credentials = seed_demo(application, settings.demo_password, settings.demo_superadmin_password)
    fixed = settings.demo_password is not None and settings.demo_superadmin_password is not None
    _print_credentials(credentials, settings.ephemeral_signing_key, fixed)
    if settings.frontend_dist is not None and not Path(settings.frontend_dist).is_dir():
        print(
            f"FRONTEND_DIST no existe: {settings.frontend_dist}. Compile la interfaz primero.",
            file=sys.stderr,
        )
        return 1
    app = build_http_app(
        application,
        tracking_interval_s=2.5,  # seguimiento programado
        frontend_dist=settings.frontend_dist,
    )
    bind_host = host or settings.host
    behind_proxy = not settings.is_local  # hospedaje con proxy inverso: confía en X-Forwarded-*
    uvicorn.run(
        app,
        host=bind_host,
        port=port or settings.port,
        log_level="info",
        proxy_headers=behind_proxy,
        forwarded_allow_ips="*" if behind_proxy else None,
    )
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "capacity"
    if command == "capacity":
        container = build_capacity_container()
        print(run_capacity_cli(container.dashboard, demo_label=DEMO_LABEL))
        return 0
    if command == "serve":
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else None
        host = argv[argv.index("--host") + 1] if "--host" in argv else None
        return _serve(host, port)
    print(f"Comando desconocido: {command}. Disponibles: capacity, serve", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
