"""Esquemas de maestros: tipos, rangos, mensajes en español y constructores de dominio."""

from __future__ import annotations

import pytest

from fleetplanner.domain.masters.builders import (
    build_corridor,
    build_customer,
    build_order,
    validate_domain,
    validate_references,
    values_of_corridor,
    values_of_customer,
)
from fleetplanner.domain.masters.catalog import (
    COMPATIBILITY,
    CORRIDOR,
    CUSTOMER,
    ENTITIES,
    ORDER,
    PARAMETERS,
    VEHICLE_TYPE,
)
from fleetplanner.domain.masters.schema import (
    FieldSpec,
    FieldType,
    coerce,
    coerce_row,
)

NUM = FieldSpec("x", "Valor", FieldType.NUMBER, min=0, exclusive_min=True, max=10)


class TestCoerce:
    def test_numbers_accept_decimal_comma_and_strings(self) -> None:
        assert coerce(NUM, "2,5") == (2.5, None)
        assert coerce(NUM, 3) == (3.0, None)

    @pytest.mark.parametrize(("raw", "message"), [
        (0, "mayor que 0"), (11, "mayor que 10"), ("abc", "debe ser un número"),
        (float("nan"), "número"),
        (True, "número"),
    ])  # fmt: skip
    def test_numeric_errors_are_explained_in_spanish(self, raw: object, message: str) -> None:
        value, error = coerce(NUM, raw)
        assert value is None and error is not None and message in error
        assert "could not" not in error and "invalid" not in error  # nunca texto interno en inglés

    def test_required_empty_values_are_rejected_and_optional_ones_allowed(self) -> None:
        assert coerce(NUM, "  ")[1] == "Valor es obligatorio."
        optional = FieldSpec("x", "Nota", FieldType.TEXT, required=False)
        assert coerce(optional, "") == (None, None)

    def test_integers_must_be_whole(self) -> None:
        spec = FieldSpec("n", "Cantidad", FieldType.INT, min=0)
        assert coerce(spec, "4") == (4, None)
        assert "entero" in (coerce(spec, "4,5")[1] or "")
        assert "no puede ser menor" in (coerce(spec, -1)[1] or "")

    def test_percent_is_kept_as_0_to_100(self) -> None:
        spec = FieldSpec("p", "Llenado", FieldType.PERCENT, min=0, max=100)
        assert coerce(spec, "85") == (85.0, None)
        assert "mayor que 100" in (coerce(spec, 101)[1] or "")

    def test_time_is_normalised_and_validated(self) -> None:
        spec = FieldSpec("t", "Hora", FieldType.TIME)
        assert coerce(spec, "8:05") == ("08:05", None)
        assert "HH:MM" in (coerce(spec, "25:00")[1] or "")

    def test_dates_must_be_iso(self) -> None:
        spec = FieldSpec("d", "Fecha", FieldType.DATE)
        assert coerce(spec, "2026-10-14") == ("2026-10-14", None)
        assert "AAAA-MM-DD" in (coerce(spec, "14/10/2026")[1] or "")
        assert "AAAA-MM-DD" in (coerce(spec, "2026-02-30")[1] or "")

    def test_select_only_accepts_listed_values(self) -> None:
        spec = FieldSpec("k", "Condición", FieldType.SELECT, options=(("own", "Propio"),))
        assert coerce(spec, "own") == ("own", None)
        assert "uno de" in (coerce(spec, "otro")[1] or "")

    def test_booleans_accept_spanish_words(self) -> None:
        spec = FieldSpec("b", "Activo", FieldType.BOOL)
        assert coerce(spec, "sí") == (True, None) and coerce(spec, "No") == (False, None)
        assert coerce(spec, "quizá")[1] is not None

    def test_text_is_trimmed_and_collapsed_and_length_limited(self) -> None:
        spec = FieldSpec("t", "Nombre", FieldType.TEXT, max_length=10)
        assert coerce(spec, "  Hola   mundo ") == ("Hola mundo", None)
        assert "máximo 10" in (coerce(spec, "x" * 11)[1] or "")

    @pytest.mark.parametrize("text", ["=1+1", "+cmd", "-2+3", "@SUM(A1)"])
    def test_text_that_looks_like_a_formula_is_rejected(self, text: str) -> None:
        spec = FieldSpec("t", "Nombre", FieldType.TEXT)
        assert "fórmula" in (coerce(spec, text)[1] or "")

    def test_negative_numbers_are_not_mistaken_for_formulas(self) -> None:
        lon = FieldSpec("lon", "Longitud", FieldType.NUMBER, min=-82, max=-66)
        assert coerce(lon, "-74,1") == (-74.1, None)


class TestRows:
    def test_all_problems_of_a_row_are_reported_together(self) -> None:
        values, issues = coerce_row(CUSTOMER, {"code": "", "name": "A", "lat": "x", "lon": "-74"})
        fields = {i.field for i in issues}
        assert {"code", "lat", "service_minutes", "window_start", "window_end"} <= fields
        assert "name" in values

    def test_unknown_columns_are_reported(self) -> None:
        _, issues = coerce_row(VEHICLE_TYPE, {"nombre_raro": 1})
        assert any(i.field == "nombre_raro" for i in issues)

    def test_key_of_joins_composite_keys(self) -> None:
        assert (
            COMPATIBILITY.key_of({"corridor_code": "URB-N", "vehicle_type": "turbo"})
            == "URB-N|turbo"
        )

    def test_catalog_is_consistent(self) -> None:
        for entity in ENTITIES.values():
            names = entity.column_names
            assert len(set(names)) == len(names)
            assert set(entity.key_fields) <= set(names)
        assert {"design_percentile", "reserve", "max_fill", "weight_delay"} <= set(PARAMETERS)


GOOD_CUSTOMER = {
    "code": "C-900", "name": "Cliente Nuevo", "address": "Calle 1", "lat": 4.65, "lon": -74.1,
    "service_minutes": 15, "window_start": "08:00", "window_end": "12:00",
}  # fmt: skip


class TestDomainBuilders:
    def test_valid_customer_is_built_and_roundtrips(self) -> None:
        customer = build_customer(GOOD_CUSTOMER)
        assert values_of_customer(customer)["window_end"] == "12:00"

    def test_criterion_11_latitude_40_and_inverted_window_are_rejected_with_explanation(
        self,
    ) -> None:
        bad = {**GOOD_CUSTOMER, "lat": 40, "window_start": "14:00", "window_end": "10:00"}
        # el esquema ya rechaza la latitud por rango; el constructor explica además la ventana
        _, issues = coerce_row(CUSTOMER, bad)
        assert any(
            i.field == "lat"
            and "Colombia" not in i.message
            and "menor" in i.message
            or "mayor" in i.message
            for i in issues
        )
        domain = validate_domain(
            CUSTOMER, {**GOOD_CUSTOMER, "window_start": "14:00", "window_end": "10:00"}
        )
        assert domain and "posterior" in domain[0].message

    def test_corridor_roundtrip_keeps_percentages_as_0_to_100(self) -> None:
        values = {
            "code": "R1", "name": "Ruta", "assigned_vehicle_type": "turbo", "one_way_km": 35,
            "average_speed_kmh": 25, "operating_hours": 10, "loading_h": 0.75, "dock_wait_h": 0.5,
            "stops": 8, "minutes_per_stop": 12, "customer_wait_h": 0.5, "fill": 85, "backhaul": 0,
        }  # fmt: skip
        assert values_of_corridor(build_corridor(values))["fill"] == pytest.approx(85)

    def test_order_priority_comes_as_text_from_the_form(self) -> None:
        order = build_order({
            "id": "P-1", "customer_code": "C-1", "kg": 100, "m3": 1,
            "window_start": "08:00", "window_end": "10:00", "priority": "1",
        })  # fmt: skip
        assert order.priority == 1


class FakeLookups:
    def __init__(self, *known: tuple[str, str]) -> None:
        self.known = set(known)

    def exists(self, entity: str, key: str) -> bool:
        return (entity, key) in self.known


class TestReferences:
    def test_missing_references_are_reported_with_the_missing_name(self) -> None:
        issues = validate_references(CORRIDOR, {"assigned_vehicle_type": "cohete"}, FakeLookups())
        assert issues and "cohete" in issues[0].message and "no existe" in issues[0].message

    def test_existing_references_pass(self) -> None:
        lookups = FakeLookups(("corridor", "R1"), ("vehicle_type", "turbo"))
        values = {"corridor_code": "R1", "vehicle_type": "turbo"}
        assert validate_references(COMPATIBILITY, values, lookups) == []

    def test_an_order_needs_an_existing_customer(self) -> None:
        assert validate_references(ORDER, {"customer_code": "C-X"}, FakeLookups())
