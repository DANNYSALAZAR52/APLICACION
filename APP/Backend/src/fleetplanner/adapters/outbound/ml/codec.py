"""Serialización de artefactos de ML.

Los artefactos son bytes que produce este mismo adaptador y que el registro guarda junto con su
SHA-256. ``load`` solo se invoca con bytes que el registro ya verificó contra ese hash (no se
deserializa nada que venga de un usuario ni de un archivo sin verificar).
"""

from __future__ import annotations

import pickle  # noqa: S403  # nosec B403 - artefactos propios con hash verificado (ver arriba)
from typing import Any


def dump(obj: Any) -> bytes:
    return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)


def load(payload: bytes) -> Any:
    """Deserializa un artefacto **ya verificado** por el registro de modelos."""
    return pickle.loads(payload)  # noqa: S301  # nosec B301 - hash verificado antes de cargar


def library_version() -> str:
    import sklearn

    return f"scikit-learn {sklearn.__version__}"
