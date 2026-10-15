"""DEMO-ONLY: datos sintéticos de ruteo (CEDI en Funza, clientes repartidos por Bogotá).

Todo es inventado y reproducible con una semilla. Las zonas son barrios reales solo como
referencia geográfica; los clientes, pedidos y pesos no corresponden a ninguna empresa.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass

from fleetplanner.adapters.outbound.demo_data.profiles import DEMO_A_SLUG, DEMO_B_SLUG
from fleetplanner.application.ports.outbound.routing import RoutingDataset
from fleetplanner.domain.routing.geo import GeoPoint
from fleetplanner.domain.routing.models import (
    Customer,
    Depot,
    Order,
    RoutingParams,
    RoutingVehicle,
    VehicleKind,
)

DEMO_ROUTING_LABEL = "DATOS DE DEMOSTRACIÓN"
DEPOT = Depot("CEDI-FUNZA", "CEDI Funza (demostración)", GeoPoint(4.7165, -74.2125))

# (zona, latitud, longitud, peso): la zona de la Calle 80 pesa más para que el cierre de la
# demostración afecte a varios clientes.
_ZONES: tuple[tuple[str, float, float, int], ...] = (
    ("Calle 80", 4.7220, -74.1000, 4),
    ("Engativá", 4.7050, -74.1100, 3),
    ("Álamos", 4.6900, -74.1000, 3),
    ("Normandía", 4.6700, -74.1100, 2),
    ("Fontibón", 4.6706, -74.1436, 3),
    ("Modelia", 4.6650, -74.1200, 2),
    ("Salitre", 4.6600, -74.1000, 2),
    ("Suba", 4.7410, -74.0830, 2),
    ("Usaquén", 4.7110, -74.0300, 1),
    ("Chapinero", 4.6486, -74.0630, 1),
    ("Teusaquillo", 4.6410, -74.0850, 1),
    ("Kennedy", 4.6290, -74.1500, 2),
    ("Puente Aranda", 4.6150, -74.1180, 2),
    ("Zona Industrial", 4.6330, -74.1000, 2),
    ("Bosa", 4.6100, -74.1900, 1),
    ("Barrios Unidos", 4.6700, -74.0780, 1),
)

# Ventanas de entrega habituales del día (minutos desde la medianoche).
_WINDOWS: tuple[tuple[int, int], ...] = (
    (7 * 60, 10 * 60),
    (8 * 60, 10 * 60),
    (8 * 60 + 30, 10 * 60 + 30),
    (9 * 60, 11 * 60),
    (9 * 60 + 30, 11 * 60 + 30),
    (10 * 60, 12 * 60),
    (11 * 60, 13 * 60),
    (7 * 60, 16 * 60),
)


@dataclass(frozen=True)
class RoutingProfile:
    seed: int
    customers: int
    active_vehicles: int
    min_kg: int = 80
    max_kg: int = 650


PROFILE_A = RoutingProfile(seed=20260712, customers=36, active_vehicles=4)
PROFILE_B = RoutingProfile(seed=20260731, customers=22, active_vehicles=3, min_kg=60, max_kg=500)


class DemoRoutingInputsReader:
    """Lector sintético y determinista de los datos de ruteo de UNA empresa."""

    def __init__(self, profile: RoutingProfile = PROFILE_A) -> None:
        self._profile = profile

    def read(self) -> RoutingDataset:
        profile = self._profile
        rng = random.Random(profile.seed)  # noqa: S311  # nosec B311 - semilla fija, demo reproducible
        zones = [z for z in _ZONES for _ in range(z[3])]
        customers: list[Customer] = []
        orders: list[Order] = []
        for i in range(1, profile.customers + 1):
            zone, lat, lon, _ = rng.choice(zones)
            start, end = rng.choice(_WINDOWS)
            code = f"C-{i:03d}"
            customer = Customer.create(
                code=code,
                name=f"Cliente {i:02d} · {zone}",
                address=f"{zone}, Bogotá (dirección ficticia)",
                lat=round(lat + rng.uniform(-0.006, 0.006), 5),
                lon=round(lon + rng.uniform(-0.006, 0.006), 5),
                window_start_min=start,
                window_end_min=end,
                service_minutes=15.0,
            )
            customers.append(customer)
            orders.append(
                Order(
                    id=f"P-{i:03d}",
                    customer_code=code,
                    kg=float(rng.randrange(profile.min_kg, profile.max_kg, 10)),
                    m3=round(rng.uniform(0.4, 4.0), 1),
                    window=customer.window,
                    priority=rng.choice((1, 2, 2, 2, 3)),
                )
            )
        vehicles = [
            RoutingVehicle(
                f"V-{n:02d}", f"T-{n:02d}", "turbo", 4500.0, VehicleKind.OWN, f"GPS-{n:02d}"
            )
            for n in range(1, profile.active_vehicles + 1)
        ]
        spare = profile.active_vehicles + 1
        vehicles.append(
            RoutingVehicle(
                f"V-{spare:02d}",
                f"T-{spare:02d} (reserva)",
                "turbo",
                4500.0,
                VehicleKind.RESERVE,
                f"GPS-{spare:02d}",
            )
        )
        vehicles.append(
            RoutingVehicle(
                "V-TER", "TER-01 (tercero)", "sencillo", 8000.0, VehicleKind.THIRD_PARTY, ""
            )
        )
        return RoutingDataset(
            DEPOT, tuple(customers), tuple(orders), tuple(vehicles), RoutingParams()
        )


def routing_reader_for_slug(slug: str) -> DemoRoutingInputsReader:
    """A y B tienen datos y tamaño distintos; otras empresas derivan su perfil del slug."""
    if slug == DEMO_A_SLUG:
        return DemoRoutingInputsReader(PROFILE_A)
    if slug == DEMO_B_SLUG:
        return DemoRoutingInputsReader(PROFILE_B)
    digest = zlib.crc32(slug.encode())
    return DemoRoutingInputsReader(
        RoutingProfile(seed=digest, customers=14 + digest % 14, active_vehicles=2 + digest % 3)
    )
