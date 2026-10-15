"""Servicio de maestros y parámetros de UNA empresa: CRUD, carga CSV, vigencias e historial.

Todo cambio pasa por los constructores de dominio (única fuente de validez), conserva el valor
anterior en el historial y avisa a quien dependa de los datos (`on_change`).
"""

from __future__ import annotations

import csv
import io
import threading
from collections.abc import Callable, Mapping
from datetime import date

from fleetplanner.application.dto.capacity import CapacityParameters
from fleetplanner.application.dto.masters import (
    CsvApplyResult,
    CsvIssue,
    CsvPreview,
    Listing,
    Lookups,
    ParameterVersionView,
    ParameterView,
    SchemaView,
)
from fleetplanner.application.ports.outbound.clock import ClockPort
from fleetplanner.application.ports.outbound.masters import (
    ChangeRecord,
    MasterDataStorePort,
    ParameterVersion,
    Row,
)
from fleetplanner.application.use_cases.masters.parameters import (
    capacity_parameters,
    routing_params,
)
from fleetplanner.domain.masters.builders import validate_domain, validate_references
from fleetplanner.domain.masters.catalog import ENTITIES, PARAMETERS
from fleetplanner.domain.masters.schema import (
    EntitySpec,
    FieldIssue,
    coerce,
    coerce_row,
    issues_text,
)
from fleetplanner.domain.routing.models import RoutingParams
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError

MAX_CSV_BYTES = 200_000
MAX_CSV_ROWS = 5000
MAX_REPORTED_ERRORS = 100
LISTING_LIMIT = 500
INITIAL_VALID_FROM = date(2000, 1, 1)

# Quién usa cada entidad: no se puede borrar algo que otro maestro referencia.
_REFERENCED_BY: dict[str, tuple[tuple[str, str], ...]] = {
    "vehicle_type": (
        ("corridor", "assigned_vehicle_type"),
        ("compatibility", "vehicle_type"),
        ("fleet", "vehicle_type"),
    ),
    "corridor": (("compatibility", "corridor_code"), ("daily_demand", "corridor_code")),
    "customer": (("order", "customer_code"),),
}


class MasterDataService:
    def __init__(
        self,
        store: MasterDataStorePort,
        clock: ClockPort,
        capacity_base: CapacityParameters,
        routing_base: RoutingParams,
    ) -> None:
        self._store = store
        self._clock = clock
        self._capacity_base = capacity_base
        self._routing_base = routing_base
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------------ eventos
    def on_change(self, listener: Callable[[], None]) -> None:
        """Registra a quien debe enterarse de que los datos cambiaron (caché, plan del día…)."""
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    # --------------------------------------------------------------- consultas
    @property
    def store(self) -> MasterDataStorePort:
        return self._store

    def exists(self, entity: str, key: str) -> bool:
        return self._store.get(entity, key) is not None

    def entity(self, name: str) -> EntitySpec:
        spec = ENTITIES.get(name)
        if spec is None:
            raise NotFoundError("Ese maestro no existe.")
        return spec

    def schema(self) -> SchemaView:
        store = self._store
        lookups = Lookups(
            vehicle_types=tuple(sorted(str(r["name"]) for r in store.rows("vehicle_type"))),
            corridors=tuple(
                sorted((str(r["code"]), str(r["name"])) for r in store.rows("corridor"))
            ),
            customers=tuple(
                sorted((str(r["code"]), str(r["name"])) for r in store.rows("customer"))
            ),
        )
        return SchemaView(tuple(ENTITIES.values()), tuple(PARAMETERS.values()), lookups)

    def list_rows(self, name: str) -> Listing:
        spec = self.entity(name)
        rows = self._store.rows(name)
        if name == "daily_demand":
            rows.sort(key=lambda r: (str(r["date"]), str(r["corridor_code"])), reverse=True)
        else:
            rows.sort(key=lambda r: spec.key_of(r).lower())
        return Listing(name, len(rows), tuple(rows[:LISTING_LIMIT]), len(rows) > LISTING_LIMIT)

    def get_row(self, name: str, key: str) -> Row:
        self.entity(name)
        row = self._store.get(name, key)
        if row is None:
            raise NotFoundError("El registro no existe.")
        return row

    # ----------------------------------------------------------------- validar
    def _validate(self, spec: EntitySpec, raw: Mapping[str, object]) -> Row:
        values, issues = coerce_row(spec, raw)
        if not issues:
            issues += validate_references(spec, values, self)
        if not issues:
            issues += validate_domain(spec, values)
        if issues:
            raise InvalidValueError(issues_text(issues))
        return values

    def _record(
        self,
        actor: str,
        entity: str,
        key: str,
        action: str,
        before: Row | None,
        after: Row | None,
        valid_from: date | None = None,
        note: str = "",
    ) -> None:
        self._store.append_history(
            ChangeRecord(
                id=self._store.next_id("CH"),
                at=self._clock.now(),
                actor=actor,
                entity=entity,
                key=key,
                action=action,
                before=before,
                after=after,
                valid_from=valid_from,
                note=note,
            )
        )

    # -------------------------------------------------------------------- CRUD
    def create(self, actor: str, name: str, raw: Mapping[str, object]) -> Row:
        spec = self.entity(name)
        with self._lock:
            values = self._validate(spec, raw)
            key = spec.key_of(values)
            if self._store.get(name, key) is not None:
                raise ConflictError(f"Ya existe {spec.label.lower()} con la clave «{key}».")
            self._store.put(name, key, values)
            self._record(actor, name, key, "create", None, values)
        self._notify()
        return values

    def update(self, actor: str, name: str, key: str, raw: Mapping[str, object]) -> Row:
        spec = self.entity(name)
        with self._lock:
            before = self._store.get(name, key)
            if before is None:
                raise NotFoundError("El registro no existe.")
            values = self._validate(spec, raw)
            if spec.key_of(values) != key:
                raise InvalidValueError(
                    "La clave de un registro no se puede cambiar; cree uno nuevo y elimine el "
                    "anterior."
                )
            self._store.put(name, key, values)
            self._record(actor, name, key, "update", before, values)
        self._notify()
        return values

    def delete(self, actor: str, name: str, key: str) -> None:
        self.entity(name)
        with self._lock:
            before = self._store.get(name, key)
            if before is None:
                raise NotFoundError("El registro no existe.")
            self._check_not_referenced(name, before)
            self._store.remove(name, key)
            self._record(actor, name, key, "delete", before, None)
        self._notify()

    def _check_not_referenced(self, name: str, row: Row) -> None:
        for other, field_name in _REFERENCED_BY.get(name, ()):
            target = str(row[ENTITIES[name].key_fields[0]])
            users = [r for r in self._store.rows(other) if str(r.get(field_name)) == target]
            if users:
                label = ENTITIES[other].plural.lower()
                raise ConflictError(
                    f"No se puede eliminar «{target}»: lo usan {len(users)} registro(s) de "
                    f"{label}. "
                    "Elimínelos o cámbielos primero."
                )

    # -------------------------------------------------------------------- CSV
    def _parse_csv(
        self, spec: EntitySpec, text: str
    ) -> tuple[list[tuple[int, Row]], list[CsvIssue], int]:
        issues: list[CsvIssue] = []
        if not spec.csv:
            raise InvalidValueError(f"{spec.plural} no admite carga por CSV.")
        if len(text.encode("utf-8")) > MAX_CSV_BYTES:
            raise InvalidValueError(
                f"El archivo supera el tamaño permitido ({MAX_CSV_BYTES // 1000} KB)."
            )
        text = text.lstrip("﻿")
        if not text.strip():
            raise InvalidValueError("El archivo está vacío.")
        first_line = text.splitlines()[0]
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        header = [h.strip() for h in next(reader, [])]
        columns = spec.column_names
        required = [f.name for f in spec.fields if f.required]
        problems = []
        if len(set(header)) != len(header):
            problems.append("El encabezado tiene columnas repetidas.")
        missing = [c for c in required if c not in header]
        if missing:
            problems.append(f"Faltan las columnas obligatorias: {', '.join(missing)}.")
        extra = [c for c in header if c not in columns]
        if extra:
            problems.append(
                f"Columnas no permitidas: {', '.join(extra)}. "
                f"Columnas válidas: {', '.join(columns)}."
            )
        if problems:
            return [], [CsvIssue(1, "", " ".join(problems))], 0

        parsed: list[tuple[int, Row]] = []
        seen: dict[str, int] = {}
        total = 0
        for number, cells in enumerate(reader, start=2):
            if not any(c.strip() for c in cells):
                continue  # fila en blanco
            total += 1
            if total > MAX_CSV_ROWS:
                issues.append(CsvIssue(number, "", f"Se admiten como máximo {MAX_CSV_ROWS} filas."))
                break
            if len(cells) != len(header):
                issues.append(
                    CsvIssue(
                        number, "", f"Tiene {len(cells)} columnas y el encabezado {len(header)}."
                    )
                )
                continue
            values, field_issues = coerce_row(spec, dict(zip(header, cells, strict=True)))
            if not field_issues:
                field_issues += validate_references(spec, values, self)
            if not field_issues:
                field_issues += validate_domain(spec, values)
            if not field_issues:
                key = spec.key_of(values)
                if key in seen:
                    field_issues.append(
                        FieldIssue(
                            "*",
                            f"La clave «{key}» está repetida (primera vez en la fila {seen[key]}).",
                        )
                    )
                else:
                    seen[key] = number
            if field_issues:
                issues.extend(
                    CsvIssue(number, i.field if i.field != "*" else "", i.message)
                    for i in field_issues
                )
            else:
                parsed.append((number, values))
        return parsed, issues, total

    def preview_csv(self, name: str, text: str) -> CsvPreview:
        spec = self.entity(name)
        parsed, issues, total = self._parse_csv(spec, text)
        create = sum(1 for _, v in parsed if self._store.get(name, spec.key_of(v)) is None)
        return CsvPreview(
            entity=name,
            rows_total=total,
            rows_valid=len(parsed),
            to_create=create,
            to_update=len(parsed) - create,
            errors=tuple(issues[:MAX_REPORTED_ERRORS]),
            errors_truncated=len(issues) > MAX_REPORTED_ERRORS,
            sample=tuple(v for _, v in parsed[:5]),
        )

    def apply_csv(self, actor: str, name: str, text: str) -> CsvApplyResult:
        """Todo o nada: si hay UN error no se aplica ninguna fila."""
        spec = self.entity(name)
        with self._lock:
            parsed, issues, total = self._parse_csv(spec, text)
            if issues or not parsed:
                raise InvalidValueError(
                    "El archivo tiene errores y no se aplicó ninguna fila. "
                    "Use la previsualización para verlos y corríjalos."
                    if issues
                    else "El archivo no tiene filas para cargar."
                )
            created = updated = 0
            for _, values in parsed:
                key = spec.key_of(values)
                before = self._store.get(name, key)
                self._store.put(name, key, values)
                self._record(actor, name, key, "csv", before, values, note=f"{total} filas")
                if before is None:
                    created += 1
                else:
                    updated += 1
        self._notify()
        return CsvApplyResult(name, created, updated)

    def export_rows(self, name: str) -> tuple[list[str], list[list[object]]]:
        """Encabezado y filas para exportar (el exportador neutraliza fórmulas)."""
        spec = self.entity(name)
        listing = self.list_rows(name)
        rows = self._store.rows(name) if listing.truncated else list(listing.rows)
        return list(spec.column_names), [[r.get(c) for c in spec.column_names] for r in rows]

    # -------------------------------------------------------------- parámetros
    def _today(self) -> date:
        return self._clock.now().date()

    def _in_force(self, key: str, on: date) -> ParameterVersion | None:
        versions = [v for v in self._store.parameter_versions(key) if v.valid_from <= on]
        return max(versions, key=lambda v: (v.valid_from, v.set_at), default=None)

    def effective_values(self, on: date | None = None) -> dict[str, object]:
        day = on or self._today()
        values: dict[str, object] = {}
        for key in PARAMETERS:
            version = self._in_force(key, day)
            if version is not None:
                values[key] = version.value
        return values

    def parameters(self) -> list[ParameterView]:
        today = self._today()
        views: list[ParameterView] = []
        for key, spec in PARAMETERS.items():
            current = self._in_force(key, today)
            if current is None:
                continue
            ordered = sorted(
                self._store.parameter_versions(key), key=lambda v: (v.valid_from, v.set_at)
            )
            views.append(
                ParameterView(
                    spec=spec,
                    value=current.value,
                    valid_from=current.valid_from,
                    versions=tuple(
                        ParameterVersionView(
                            value=v.value,
                            valid_from=v.valid_from,
                            set_by=v.set_by,
                            set_at=v.set_at,
                            note=v.note,
                            in_force=v is current,
                            scheduled=v.valid_from > today,
                        )
                        for v in reversed(ordered)
                    ),
                )
            )
        return views

    def seed_parameter(self, key: str, value: object, actor: str = "sistema") -> None:
        self._store.add_parameter_version(
            ParameterVersion(
                key, value, INITIAL_VALID_FROM, actor, self._clock.now(), "Valor inicial de la demo"
            )
        )

    def set_parameter(
        self,
        actor: str,
        key: str,
        raw_value: object,
        valid_from: date | None = None,
        note: str = "",
    ) -> ParameterView:
        spec = PARAMETERS.get(key)
        if spec is None:
            raise NotFoundError("Ese parámetro no existe.")
        value, error = coerce(spec.field, raw_value)
        if error or value is None:
            raise InvalidValueError(error or f"{spec.label} es obligatorio.")
        with self._lock:
            today = self._today()
            start = valid_from or today
            if start < today:
                raise InvalidValueError(
                    "La vigencia no puede estar en el pasado: el historial no se reescribe."
                )
            before = self._in_force(key, start)
            candidate = ParameterVersion(
                key, value, start, actor, self._clock.now(), note.strip()[:200]
            )
            # El conjunto completo debe seguir siendo válido en la fecha de vigencia.
            trial = self.effective_values(start)
            trial[key] = value
            self._validate_parameter_set(trial)
            self._store.add_parameter_version(candidate)
            self._record(
                actor,
                "parameter",
                key,
                "parameter",
                {"value": before.value} if before else None,
                {"value": value},
                valid_from=start,
                note=candidate.note,
            )
        self._notify()
        return next(v for v in self.parameters() if v.spec.key == key)

    def _validate_parameter_set(self, values: Mapping[str, object]) -> None:
        try:
            capacity_parameters(values, self._capacity_base)
            routing_params(values, self._routing_base)
        except InvalidValueError as error:
            raise InvalidValueError(
                f"Con ese valor los parámetros quedan inconsistentes: {error}"
            ) from error

    # --------------------------------------------------------------- historial
    def history(self, limit: int = 100, entity: str | None = None) -> list[ChangeRecord]:
        if entity is not None and entity != "parameter":
            self.entity(entity)
        return self._store.history(max(1, min(limit, 500)), entity)
