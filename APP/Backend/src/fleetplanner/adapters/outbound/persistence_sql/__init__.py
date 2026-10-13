"""Persistencia SQLAlchemy/PostgreSQL — PENDIENTE (comentada a propósito en la demo).

Decisión del usuario: para la demo no se desarrolla la base de datos; los adaptadores reales
quedan descritos aquí y la demo usa ``persistence_memory`` (DEMO-ONLY, ver ``docs/DEUDA_DEMO.md``).

Cuando se active, este paquete debe contener, sin importar otros adaptadores:

    # from sqlalchemy import ...                       # ORM != entidades de dominio
    #
    # class CapacityResultRow(Base):                   # tabla `capacity_result`
    #     __tablename__ = "capacity_result"
    #     id, run_at (timestamptz), method, vehicle_type, year, required_fleet,
    #     algorithm_version, parameters (JSONB), created_at, updated_at, updated_by
    #
    # class SqlCapacityResultRepository:               # implementa CapacityResultWriter/Reader
    #     def __init__(self, session): ...             # sesión ligada al tenant autenticado
    #     def save_all(self, results): ...             # mapeo explícito dominio -> ORM
    #     def list_all(self): ...
    #
    # class SqlCapacityInputsReader:                   # implementa CapacityInputsReader
    #     ...                                          # maestros, parámetros con vigencia, demanda

Topología prevista (ver ``infra/docker-compose.yml``, comentada): ``pg-control``,
``pg-tenant-a`` y ``pg-tenant-b``; migraciones Alembic ``control_plane`` y ``tenant``.
"""
