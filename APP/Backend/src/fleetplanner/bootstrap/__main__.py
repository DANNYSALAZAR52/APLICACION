"""Punto de entrada de la demo.

* ``python -m fleetplanner.bootstrap capacity`` — informe de capacidad en consola.
* ``python -m fleetplanner.bootstrap serve [--port 8000]`` — API HTTP con datos sembrados.
"""

from __future__ import annotations

import sys

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


def _print_credentials(credentials: list[SeedCredential], ephemeral_key: bool) -> None:
    print("=" * 78)
    print(f"  {DEMO_LABEL} — usuarios sembrados (contraseñas aleatorias, SE MUESTRAN UNA VEZ)")
    print("=" * 78)
    print(f"  {'empresa':<18}{'usuario':<14}{'rol':<14}contraseña")
    for c in credentials:
        print(f"  {c.tenant:<18}{c.username:<14}{c.role.value:<14}{c.password}")
    print("-" * 78)
    print("  Anótelas ahora: no se guardan en disco ni se vuelven a mostrar.")
    if ephemeral_key:
        print("  Clave de firma efímera (solo local): las sesiones caducan al reiniciar.")
    print("=" * 78, flush=True)


def _serve(port: int) -> int:
    import uvicorn

    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"Configuración inválida: {error}", file=sys.stderr)
        return 1
    application = build_application(settings)
    credentials = seed_demo(application)
    _print_credentials(credentials, settings.ephemeral_signing_key)
    uvicorn.run(build_http_app(application), host="127.0.0.1", port=port, log_level="info")
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "capacity"
    if command == "capacity":
        container = build_capacity_container()
        print(run_capacity_cli(container.dashboard, demo_label=DEMO_LABEL))
        return 0
    if command == "serve":
        port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8000
        return _serve(port)
    print(f"Comando desconocido: {command}. Disponibles: capacity, serve", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
