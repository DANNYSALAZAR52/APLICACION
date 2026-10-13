"""DEMO-ONLY: perfil de datos sintéticos por empresa (Empresa Demo A y B son distintas)."""

from __future__ import annotations

import zlib

from fleetplanner.adapters.outbound.demo_data.capacity_dataset import DemoCapacityInputsReader

DEMO_A_SLUG = "empresa-demo-a"
DEMO_B_SLUG = "empresa-demo-b"


def capacity_reader_for_slug(slug: str) -> DemoCapacityInputsReader:
    """Lector sintético determinista para una empresa.

    A y B tienen datos, tamaño y flota distintos para demostrar la separación total. Cualquier
    otra empresa (alta desde la pantalla de administración) recibe un perfil derivado de su slug
    con un hash estable, de modo que es reproducible entre ejecuciones.
    """
    if slug == DEMO_A_SLUG:
        return DemoCapacityInputsReader()
    if slug == DEMO_B_SLUG:
        return DemoCapacityInputsReader(
            seed=20260731,
            demand_scale=0.55,
            missing_rate=0.10,
            current_fleet={"turbo": 8, "sencillo": 6, "doble_troque": 4, "tractomula": 7},
        )
    digest = zlib.crc32(slug.encode())
    scale = 0.5 + (digest % 70) / 100  # 0,50 a 1,19
    fleet = {
        "turbo": round(15 * scale),
        "sencillo": round(10 * scale),
        "doble_troque": round(8 * scale),
        "tractomula": round(12 * scale),
    }
    return DemoCapacityInputsReader(seed=digest, demand_scale=scale, current_fleet=fleet)
