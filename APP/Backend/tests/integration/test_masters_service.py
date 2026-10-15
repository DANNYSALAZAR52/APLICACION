"""Maestros y parámetros: CRUD validado, referencias, CSV, vigencias y efecto en los cálculos."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fleetplanner.adapters.outbound.demo_data import capacity_reader_for_slug
from fleetplanner.bootstrap.container import build_capacity_container
from fleetplanner.domain.shared.errors import ConflictError, InvalidValueError, NotFoundError
from masters_helpers import Masters, make_masters

TYPE = {
    "name": "furgon", "capacity_t": 1.5, "capacity_m3": 9, "pallets": 3,
    "fixed_cost_month": 2_000_000, "variable_cost_per_km": 700, "third_party_daily_rate": 300_000,
}  # fmt: skip
CUSTOMER = {
    "code": "C-900", "name": "Cliente Nuevo", "address": "Calle 1", "lat": 4.65, "lon": -74.1,
    "service_minutes": 15, "window_start": "08:00", "window_end": "12:00",
}  # fmt: skip


@pytest.fixture
def m() -> Masters:
    return make_masters()


class TestSeedingMatchesTheOriginalData:
    def test_the_editable_store_reproduces_the_original_capacity_results(self, m: Masters) -> None:
        original = build_capacity_container(
            reader=capacity_reader_for_slug("empresa-demo-b"), clock=m.clock
        ).dashboard.execute()
        edited = m.dashboard()
        assert (
            edited.balance.requirement.total_required == original.balance.requirement.total_required
        )
        assert (
            edited.balance.requirement.required_by_type
            == original.balance.requirement.required_by_type
        )
        assert edited.lean.total_required == original.lean.total_required
        assert edited.monte_carlo.p95_total == original.monte_carlo.p95_total

    def test_all_parameters_start_with_an_initial_version(self, m: Masters) -> None:
        views = m.service.parameters()
        assert {v.spec.key for v in views} >= {
            "design_percentile",
            "reserve",
            "max_fill",
            "departure",
        }
        assert all(
            len(v.versions) == 1 and v.versions[0].note.startswith("Valor inicial") for v in views
        )


class TestCrud:
    def test_create_validates_stores_and_records_history(self, m: Masters) -> None:
        row = m.service.create("admin", "vehicle_type", TYPE)
        assert row["name"] == "furgon"
        assert m.service.get_row("vehicle_type", "furgon")["capacity_t"] == 1.5
        change = m.service.history(1)[0]
        assert (change.action, change.entity, change.key, change.actor) == (
            "create",
            "vehicle_type",
            "furgon",
            "admin",
        )
        assert change.before is None and change.after == row

    def test_a_duplicate_key_is_a_conflict(self, m: Masters) -> None:
        m.service.create("admin", "vehicle_type", TYPE)
        with pytest.raises(ConflictError, match="Ya existe"):
            m.service.create("admin", "vehicle_type", TYPE)

    def test_every_problem_is_reported_at_once_in_spanish(self, m: Masters) -> None:
        bad = {**TYPE, "capacity_t": 0, "pallets": "x", "name": ""}
        with pytest.raises(InvalidValueError) as err:
            m.service.create("admin", "vehicle_type", bad)
        text = str(err.value)
        assert "Nombre es obligatorio" in text and "Capacidad (t) debe ser mayor que 0" in text
        assert "Pallets debe ser un número" in text

    def test_update_keeps_the_previous_value_in_the_history(self, m: Masters) -> None:
        m.service.create("admin", "vehicle_type", TYPE)
        m.service.update("jefe", "vehicle_type", "furgon", {**TYPE, "capacity_t": 2.0})
        change = m.service.history(1)[0]
        assert change.action == "update" and change.actor == "jefe"
        assert change.before["capacity_t"] == 1.5 and change.after["capacity_t"] == 2.0  # type: ignore[index]

    def test_the_key_cannot_be_changed_by_an_update(self, m: Masters) -> None:
        m.service.create("admin", "vehicle_type", TYPE)
        with pytest.raises(InvalidValueError, match="no se puede cambiar"):
            m.service.update("admin", "vehicle_type", "furgon", {**TYPE, "name": "otro"})

    def test_updating_or_reading_an_unknown_record_is_not_found(self, m: Masters) -> None:
        with pytest.raises(NotFoundError):
            m.service.update("admin", "vehicle_type", "nada", TYPE)
        with pytest.raises(NotFoundError):
            m.service.get_row("vehicle_type", "nada")
        with pytest.raises(NotFoundError, match="Ese maestro"):
            m.service.list_rows("inventado")

    def test_delete_removes_and_records_the_old_value(self, m: Masters) -> None:
        m.service.create("admin", "vehicle_type", TYPE)
        m.service.delete("admin", "vehicle_type", "furgon")
        assert m.service.store.get("vehicle_type", "furgon") is None
        change = m.service.history(1)[0]
        assert change.action == "delete" and change.before is not None and change.after is None

    def test_listing_is_sorted_and_demand_shows_the_newest_first(self, m: Masters) -> None:
        names = [r["name"] for r in m.service.list_rows("vehicle_type").rows]
        assert names == sorted(names, key=str.lower)
        dates = [r["date"] for r in m.service.list_rows("daily_demand").rows]
        assert dates == sorted(dates, reverse=True)

    def test_listing_is_capped_but_reports_the_total(self, m: Masters) -> None:
        listing = m.service.list_rows("daily_demand")
        assert listing.total > 500 and len(listing.rows) == 500 and listing.truncated


class TestReferences:
    def test_a_corridor_needs_an_existing_vehicle_type(self, m: Masters) -> None:
        corridor = {
            **m.service.get_row("corridor", "URB-N"),
            "code": "NUEVA",
            "assigned_vehicle_type": "cohete",
        }
        with pytest.raises(InvalidValueError, match="«cohete» no existe"):
            m.service.create("admin", "corridor", corridor)

    def test_a_vehicle_type_in_use_cannot_be_deleted(self, m: Masters) -> None:
        with pytest.raises(ConflictError, match="lo usan"):
            m.service.delete("admin", "vehicle_type", "turbo")
        assert m.service.store.get("vehicle_type", "turbo") is not None

    def test_a_corridor_with_compatibilities_or_demand_cannot_be_deleted(self, m: Masters) -> None:
        with pytest.raises(ConflictError, match="Elimínelos o cámbielos primero"):
            m.service.delete("admin", "corridor", "URB-N")

    def test_a_customer_with_orders_cannot_be_deleted_but_a_free_one_can(self, m: Masters) -> None:
        with pytest.raises(ConflictError):
            m.service.delete("admin", "customer", "C-001")
        m.service.create("admin", "customer", CUSTOMER)
        m.service.delete("admin", "customer", "C-900")

    def test_an_order_needs_an_existing_customer(self, m: Masters) -> None:
        order = {"id": "P-900", "customer_code": "NO-EXISTE", "kg": 100, "m3": 1,
                 "window_start": "08:00", "window_end": "10:00", "priority": "2"}  # fmt: skip
        with pytest.raises(InvalidValueError, match="no existe"):
            m.service.create("admin", "order", order)

    def test_compatibility_links_two_existing_records(self, m: Masters) -> None:
        m.service.create(
            "admin", "compatibility", {"corridor_code": "URB-N", "vehicle_type": "doble_troque"}
        )
        assert m.service.store.get("compatibility", "URB-N|doble_troque") is not None


class TestCriterion11:
    """Criterio 11: latitud 40 y ventana 14:00–10:00 se rechazan, explicando cómo corregir."""

    def test_both_problems_are_reported_in_one_pass(self, m: Masters) -> None:
        bad = {**CUSTOMER, "lat": 40, "window_start": "14:00", "window_end": "10:00"}
        with pytest.raises(InvalidValueError) as err:
            m.service.create("admin", "customer", bad)
        text = str(err.value)
        assert "Latitud no puede ser mayor que 13,5" in text
        assert "14:00–10:00" in text and "posterior" in text
        assert m.service.store.get("customer", "C-900") is None  # no se guardó nada

    def test_a_valid_customer_is_accepted_and_reaches_the_next_routing_day(
        self, m: Masters
    ) -> None:
        m.service.create("admin", "customer", CUSTOMER)
        order = {
            "id": "P-900",
            "customer_code": "C-900",
            "kg": 120,
            "m3": 1,
            "window_start": "08:00",
            "window_end": "16:00",
            "priority": "2",
        }
        m.service.create("admin", "order", order)
        routing = m.routing()
        plan = routing.workspace.day.start("t")
        assert "P-900" in {i for r in plan.routes for i in r.pending_order_ids()}


class TestCsv:
    HEADER = "code,name,address,lat,lon,service_minutes,window_start,window_end,restrictions"

    def csv(self, *rows: str, header: str | None = None) -> str:
        return "\n".join([header or self.HEADER, *rows])

    def test_preview_counts_new_and_updated_rows_without_changing_anything(
        self, m: Masters
    ) -> None:
        text = self.csv(
            "C-901,Uno,Calle 1,4.65,-74.1,15,08:00,12:00,",
            "C-001,Cliente existente,Calle 2,4.66,-74.1,15,08:00,12:00,",
        )
        preview = m.service.preview_csv("customer", text)
        assert (preview.rows_total, preview.rows_valid, preview.to_create, preview.to_update) == (
            2,
            2,
            1,
            1,
        )
        assert preview.can_apply and len(preview.sample) == 2
        assert m.service.store.get("customer", "C-901") is None

    def test_apply_creates_and_updates_and_records_each_row(self, m: Masters) -> None:
        text = self.csv(
            "C-901,Uno,Calle 1,4.65,-74.1,15,08:00,12:00,",
            "C-001,Renombrado,Calle 2,4.66,-74.1,15,08:00,12:00,",
        )
        result = m.service.apply_csv("admin", "customer", text)
        assert (result.created, result.updated) == (1, 1)
        assert m.service.get_row("customer", "C-001")["name"] == "Renombrado"
        csv_changes = [c for c in m.service.history(10) if c.action == "csv"]
        assert {c.key for c in csv_changes} == {"C-901", "C-001"}
        assert next(c for c in csv_changes if c.key == "C-001").before is not None

    def test_errors_are_reported_per_row_and_column_with_row_numbers(self, m: Masters) -> None:
        text = self.csv(
            "C-901,Uno,Calle 1,40,-74.1,15,08:00,12:00,",
            "C-902,Dos,Calle 1,4.6,-74.1,15,14:00,10:00,",
            "C-903,Tres,Calle 1,x,-74.1,15,08:00,12:00,",
        )
        preview = m.service.preview_csv("customer", text)
        assert not preview.can_apply and preview.rows_valid == 0
        by_row = {(e.row, e.column) for e in preview.errors}
        assert (2, "lat") in by_row and (3, "window_end") in by_row and (4, "lat") in by_row
        assert any("posterior" in e.message for e in preview.errors if e.row == 3)

    def test_one_bad_row_blocks_the_whole_file(self, m: Masters) -> None:
        text = self.csv(
            "C-901,Uno,Calle 1,4.65,-74.1,15,08:00,12:00,",
            "C-902,Dos,Calle 1,99,-74.1,15,08:00,12:00,",
        )
        with pytest.raises(InvalidValueError, match="no se aplicó ninguna fila"):
            m.service.apply_csv("admin", "customer", text)
        assert m.service.store.get("customer", "C-901") is None  # ni la fila buena

    def test_duplicate_keys_inside_the_file_are_reported(self, m: Masters) -> None:
        row = "C-901,Uno,Calle 1,4.65,-74.1,15,08:00,12:00,"
        preview = m.service.preview_csv("customer", self.csv(row, row))
        assert any("repetida" in e.message and e.row == 3 for e in preview.errors)

    @pytest.mark.parametrize(
        ("header", "message"),
        [
            ("code,name,lat", "Faltan las columnas obligatorias"),
            (HEADER + ",extra", "Columnas no permitidas: extra"),
            (HEADER + ",code", "columnas repetidas"),
        ],
    )
    def test_the_header_is_validated(self, m: Masters, header: str, message: str) -> None:
        preview = m.service.preview_csv("customer", header + "\nC-901,Uno")
        assert not preview.can_apply and message in preview.errors[0].message

    def test_semicolon_delimiter_bom_decimal_comma_and_blank_lines_are_accepted(
        self, m: Masters
    ) -> None:
        text = (
            "﻿"
            + self.HEADER.replace(",", ";")
            + "\n\nC-901;Uno;Calle 1;4,65;-74,1;15;08:00;12:00;\n"
        )
        preview = m.service.preview_csv("customer", text)
        assert preview.can_apply and preview.rows_valid == 1

    def test_rows_with_the_wrong_number_of_columns_are_reported(self, m: Masters) -> None:
        preview = m.service.preview_csv("customer", self.csv("C-901,Uno,Calle 1"))
        assert "columnas" in preview.errors[0].message and preview.errors[0].row == 2

    def test_text_that_looks_like_a_formula_is_rejected(self, m: Masters) -> None:
        preview = m.service.preview_csv(
            "customer", self.csv("C-901,=HYPERLINK(1),Calle 1,4.65,-74.1,15,08:00,12:00,")
        )
        assert any("fórmula" in e.message and e.column == "name" for e in preview.errors)

    def test_negative_longitudes_are_not_mistaken_for_formulas(self, m: Masters) -> None:
        assert m.service.preview_csv(
            "customer", self.csv("C-901,Uno,Calle 1,4.65,-74.1,15,08:00,12:00,")
        ).can_apply

    def test_unknown_references_are_reported_per_row(self, m: Masters) -> None:
        header = "id,customer_code,kg,m3,window_start,window_end,priority"
        preview = m.service.preview_csv("order", f"{header}\nP-900,NO-EXISTE,100,1,08:00,10:00,2")
        assert any("no existe" in e.message and e.row == 2 for e in preview.errors)

    def test_empty_oversized_and_unsupported_files_are_rejected(self, m: Masters) -> None:
        with pytest.raises(InvalidValueError, match="vacío"):
            m.service.preview_csv("customer", "  \n")
        with pytest.raises(InvalidValueError, match="tamaño permitido"):
            m.service.preview_csv("customer", "x" * 250_000)
        with pytest.raises(NotFoundError):
            m.service.preview_csv("inventado", "a")

    def test_too_many_rows_are_rejected(self, m: Masters) -> None:
        start = date(2000, 1, 1)
        rows = [f"URB-N,{(start + timedelta(days=i)).isoformat()},5" for i in range(5002)]
        preview = m.service.preview_csv(
            "daily_demand", "corridor_code,date,tons\n" + "\n".join(rows)
        )
        assert any("como máximo 5000 filas" in e.message for e in preview.errors)
        assert not preview.can_apply

    def test_the_demand_csv_loads_history_and_a_missing_day_stays_missing(self, m: Masters) -> None:
        text = "corridor_code,date,tons\nURB-N,2026-11-01,31.5\nURB-N,2026-11-03,29"
        m.service.apply_csv("admin", "daily_demand", text)
        series = m.capacity_reader().load().demand["URB-N"].observations
        assert series[date(2026, 11, 1)] == 31.5 and date(2026, 11, 2) not in series

    def test_errors_are_capped(self, m: Masters) -> None:
        rows = [f"C-{i:03d},N,Calle,99,-74.1,15,08:00,12:00," for i in range(150)]
        preview = m.service.preview_csv("customer", self.csv(*rows))
        assert len(preview.errors) == 100 and preview.errors_truncated


class TestParameters:
    def test_a_change_takes_effect_and_keeps_the_previous_version(self, m: Masters) -> None:
        before = m.service.effective_values()["reserve"]
        view = m.service.set_parameter("admin", "reserve", 12, note="Mayor reserva")
        assert view.value == 12.0 and before == 8.0
        assert len(view.versions) == 2
        old = view.versions[-1]
        assert old.value == 8.0 and not old.in_force
        record = m.service.history(1)[0]
        assert (
            record.action == "parameter"
            and record.before == {"value": 8.0}
            and record.after == {"value": 12.0}
        )

    def test_a_future_effective_date_is_scheduled_and_not_used_until_then(self, m: Masters) -> None:
        tomorrow = m.clock.now().date() + timedelta(days=1)
        view = m.service.set_parameter("admin", "reserve", 15, valid_from=tomorrow)
        assert view.value == 8.0  # hoy sigue vigente el anterior
        assert next(v for v in view.versions if v.scheduled).value == 15.0
        m.clock.advance(timedelta(days=1))
        assert m.service.effective_values()["reserve"] == 15.0

    def test_the_past_cannot_be_rewritten(self, m: Masters) -> None:
        yesterday = m.clock.now().date() - timedelta(days=1)
        with pytest.raises(InvalidValueError, match="no se reescribe"):
            m.service.set_parameter("admin", "reserve", 15, valid_from=yesterday)

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("reserve", 120),
            ("days_per_month", 40),
            ("max_fill", 5),
            ("departure", "25:00"),
            ("weight_delay", -1),
        ],
    )
    def test_out_of_range_values_are_rejected_in_spanish(
        self, m: Masters, key: str, value: object
    ) -> None:
        with pytest.raises(InvalidValueError):
            m.service.set_parameter("admin", key, value)
        assert m.service.effective_values()[key] != value

    def test_values_that_make_the_set_inconsistent_are_rejected(self, m: Masters) -> None:
        with pytest.raises(InvalidValueError, match="inconsistentes"):
            m.service.set_parameter("admin", "shift_end", "05:00")  # antes de la salida (06:00)

    def test_unknown_parameter_is_not_found(self, m: Masters) -> None:
        with pytest.raises(NotFoundError):
            m.service.set_parameter("admin", "inventado", 1)

    def test_parameters_change_the_capacity_results(self, m: Masters) -> None:
        base = m.dashboard().balance.requirement.total_required
        m.service.set_parameter("admin", "reserve", 30)
        assert m.dashboard().balance.requirement.total_required > base

    def test_percentiles_are_applied_as_fractions(self, m: Masters) -> None:
        m.service.set_parameter("admin", "design_percentile", 75)
        assert m.capacity_reader().load().parameters.design_percentile.fraction == 0.75

    def test_routing_parameters_apply_to_the_next_day(self, m: Masters) -> None:
        m.service.set_parameter("admin", "max_fill", 70)
        routing = m.routing()
        routing.workspace.day.start("t")
        assert routing.workspace.core.params.max_fill == 0.7
        assert (
            routing.workspace.core.params.operational_capacity_kg(
                routing.workspace.core.vehicle("V-01")
            )
            == 3150
        )


class TestOtherEffects:
    def test_fleet_changes_move_the_gap(self, m: Masters) -> None:
        before = m.dashboard().balance.requirement.gap_by_type["turbo"]
        m.service.update("admin", "fleet", "turbo", {"vehicle_type": "turbo", "count": 40})
        assert m.dashboard().balance.requirement.gap_by_type["turbo"] == before + (
            40 - m.capacity_base.current_fleet["turbo"]
        )

    def test_removing_a_compatibility_changes_what_the_mix_can_use(self, m: Masters) -> None:
        m.service.delete("admin", "compatibility", "SAB-01|doble_troque")
        matrix = m.capacity_reader().load().compatibility
        assert not matrix.is_allowed("SAB-01", "doble_troque") and matrix.is_allowed(
            "SAB-01", "turbo"
        )

    def test_changes_notify_listeners_so_caches_can_be_invalidated(self, m: Masters) -> None:
        calls: list[int] = []
        m.service.on_change(lambda: calls.append(1))
        m.service.create("admin", "vehicle_type", TYPE)
        m.service.set_parameter("admin", "reserve", 10)
        m.service.update("admin", "vehicle_type", "furgon", {**TYPE, "pallets": 4})
        assert len(calls) == 3

    def test_failed_changes_do_not_notify_or_leave_history(self, m: Masters) -> None:
        calls: list[int] = []
        m.service.on_change(lambda: calls.append(1))
        before = len(m.service.history(500))
        with pytest.raises(InvalidValueError):
            m.service.create("admin", "vehicle_type", {**TYPE, "capacity_t": -1})
        assert calls == [] and len(m.service.history(500)) == before

    def test_history_can_be_filtered_by_entity_and_limited(self, m: Masters) -> None:
        m.service.create("admin", "vehicle_type", TYPE)
        m.service.set_parameter("admin", "reserve", 9)
        assert {c.entity for c in m.service.history(10, "vehicle_type")} == {"vehicle_type"}
        assert [c.entity for c in m.service.history(1)] == ["parameter"]
        with pytest.raises(NotFoundError):
            m.service.history(10, "inventado")

    def test_export_rows_use_the_schema_columns(self, m: Masters) -> None:
        header, rows = m.service.export_rows("vehicle_type")
        assert header[0] == "name" and len(rows) == 4 and len(rows[0]) == len(header)
