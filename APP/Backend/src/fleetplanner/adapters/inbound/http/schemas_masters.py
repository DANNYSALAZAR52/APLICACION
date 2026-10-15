"""Esquemas HTTP de maestros. Rechazan campos desconocidos (ningún `tenant_id` en el cuerpo)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from fleetplanner.adapters.inbound.http.schemas import DEMO_LABEL, StrictModel
from fleetplanner.application.dto.masters import (
    CsvApplyResult,
    CsvPreview,
    Listing,
    ParameterView,
    SchemaView,
)
from fleetplanner.application.ports.outbound.masters import ChangeRecord
from fleetplanner.application.use_cases.masters.service import MAX_CSV_BYTES
from fleetplanner.domain.masters.schema import EntitySpec, FieldSpec


class FieldOut(BaseModel):
    name: str
    label: str
    type: str
    required: bool
    min: float | None
    max: float | None
    exclusive_min: bool
    max_length: int
    options: list[tuple[str, str]]
    options_from: str | None
    help: str
    unit: str


class EntityOut(BaseModel):
    name: str
    label: str
    plural: str
    description: str
    key_fields: list[str]
    csv: bool
    fields: list[FieldOut]


class ParameterSpecOut(BaseModel):
    key: str
    area: str
    label: str
    help: str
    field: FieldOut


class LookupsOut(BaseModel):
    vehicle_types: list[str]
    corridors: list[tuple[str, str]]
    customers: list[tuple[str, str]]


class MasterSchemaOut(BaseModel):
    demo_label: str
    entities: list[EntityOut]
    parameters: list[ParameterSpecOut]
    lookups: LookupsOut


class RowsOut(BaseModel):
    entity: str
    total: int
    rows: list[dict[str, Any]]
    truncated: bool


class RowIn(StrictModel):
    values: dict[str, str | int | float | bool | None]

    @field_validator("values")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 30:
            raise ValueError("demasiados campos")
        return value


class CsvIn(StrictModel):
    content: str = Field(min_length=1, max_length=MAX_CSV_BYTES + 10_000)


class CsvIssueOut(BaseModel):
    row: int
    column: str
    message: str


class CsvPreviewOut(BaseModel):
    entity: str
    rows_total: int
    rows_valid: int
    to_create: int
    to_update: int
    errors: list[CsvIssueOut]
    errors_truncated: bool
    sample: list[dict[str, Any]]
    can_apply: bool


class CsvApplyOut(BaseModel):
    entity: str
    created: int
    updated: int


class ParameterVersionOut(BaseModel):
    value: Any
    valid_from: date
    set_by: str
    set_at: datetime
    note: str
    in_force: bool
    scheduled: bool


class ParameterOut(BaseModel):
    key: str
    area: str
    label: str
    help: str
    field: FieldOut
    value: Any
    valid_from: date
    versions: list[ParameterVersionOut]


class ParameterIn(StrictModel):
    value: str | int | float
    valid_from: date | None = None
    note: str = Field(default="", max_length=200)


class ChangeOut(BaseModel):
    id: str
    at: datetime
    actor: str
    entity: str
    key: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    valid_from: date | None
    note: str


# ---------------------------------------------------------------------- mapeos
def _field(f: FieldSpec) -> FieldOut:
    return FieldOut(
        name=f.name,
        label=f.label,
        type=f.type.value,
        required=f.required,
        min=f.min,
        max=f.max,
        exclusive_min=f.exclusive_min,
        max_length=f.max_length,
        options=list(f.options),
        options_from=f.options_from,
        help=f.help,
        unit=f.unit,
    )


def _entity(e: EntitySpec) -> EntityOut:
    return EntityOut(
        name=e.name,
        label=e.label,
        plural=e.plural,
        description=e.description,
        key_fields=list(e.key_fields),
        csv=e.csv,
        fields=[_field(f) for f in e.fields],
    )


def schema_out(s: SchemaView) -> MasterSchemaOut:
    return MasterSchemaOut(
        demo_label=DEMO_LABEL,
        entities=[_entity(e) for e in s.entities],
        parameters=[
            ParameterSpecOut(
                key=p.key, area=p.area, label=p.label, help=p.help, field=_field(p.field)
            )
            for p in s.parameters
        ],
        lookups=LookupsOut(
            vehicle_types=list(s.lookups.vehicle_types),
            corridors=list(s.lookups.corridors),
            customers=list(s.lookups.customers),
        ),
    )


def rows_out(listing: Listing) -> RowsOut:
    return RowsOut(
        entity=listing.entity,
        total=listing.total,
        rows=[dict(r) for r in listing.rows],
        truncated=listing.truncated,
    )


def preview_out(p: CsvPreview) -> CsvPreviewOut:
    return CsvPreviewOut(
        entity=p.entity,
        rows_total=p.rows_total,
        rows_valid=p.rows_valid,
        to_create=p.to_create,
        to_update=p.to_update,
        errors=[CsvIssueOut(row=i.row, column=i.column, message=i.message) for i in p.errors],
        errors_truncated=p.errors_truncated,
        sample=[dict(r) for r in p.sample],
        can_apply=p.can_apply,
    )


def apply_out(r: CsvApplyResult) -> CsvApplyOut:
    return CsvApplyOut(entity=r.entity, created=r.created, updated=r.updated)


def parameter_out(v: ParameterView) -> ParameterOut:
    return ParameterOut(
        key=v.spec.key,
        area=v.spec.area,
        label=v.spec.label,
        help=v.spec.help,
        field=_field(v.spec.field),
        value=v.value,
        valid_from=v.valid_from,
        versions=[
            ParameterVersionOut(
                value=x.value,
                valid_from=x.valid_from,
                set_by=x.set_by,
                set_at=x.set_at,
                note=x.note,
                in_force=x.in_force,
                scheduled=x.scheduled,
            )
            for x in v.versions
        ],
    )


def change_out(c: ChangeRecord) -> ChangeOut:
    return ChangeOut(
        id=c.id,
        at=c.at,
        actor=c.actor,
        entity=c.entity,
        key=c.key,
        action=c.action,
        before=dict(c.before) if c.before is not None else None,
        after=dict(c.after) if c.after is not None else None,
        valid_from=c.valid_from,
        note=c.note,
    )
