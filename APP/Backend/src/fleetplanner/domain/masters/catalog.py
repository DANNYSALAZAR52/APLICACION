"""Catálogo de maestros y parámetros editables (DOCS.MD §5.1 y §5.2)."""

from __future__ import annotations

from dataclasses import dataclass

from fleetplanner.domain.masters.schema import EntitySpec, FieldSpec, FieldType

T, N, INT, P = FieldType.TEXT, FieldType.NUMBER, FieldType.INT, FieldType.PERCENT

VEHICLE_TYPE = EntitySpec(
    name="vehicle_type",
    label="Tipo de vehículo",
    plural="Tipos de vehículo",
    description="Capacidades y costos de cada tipo (turbo, sencillo, doble troque, tractomula…).",
    key_fields=("name",),
    fields=(
        FieldSpec("name", "Nombre", T, max_length=40, help="Identificador del tipo, p. ej. turbo."),
        FieldSpec("capacity_t", "Capacidad (t)", N, min=0, exclusive_min=True, unit="t"),
        FieldSpec("capacity_m3", "Capacidad (m³)", N, min=0, exclusive_min=True, unit="m³"),
        FieldSpec("pallets", "Pallets", INT, min=0, max=200),
        FieldSpec("fixed_cost_month", "Costo fijo mensual", N, min=0, unit="COP/mes"),
        FieldSpec("variable_cost_per_km", "Costo variable por km", N, min=0, unit="COP/km"),
        FieldSpec("third_party_daily_rate", "Tarifa diaria de tercero", N, min=0, unit="COP/día"),
    ),
)

CORRIDOR = EntitySpec(
    name="corridor",
    label="Corredor o ruta",
    plural="Corredores",
    description="Ruta con sus tiempos de ciclo, usada para dimensionar la flota.",
    key_fields=("code",),
    fields=(
        FieldSpec("code", "Código", T, max_length=20),
        FieldSpec("name", "Nombre", T, max_length=80),
        FieldSpec(
            "assigned_vehicle_type",
            "Tipo de vehículo asignado",
            FieldType.SELECT,
            options_from="vehicle_types",
        ),  # fmt: skip
        FieldSpec("one_way_km", "Km de ida", N, min=0, exclusive_min=True, unit="km"),
        FieldSpec(
            "average_speed_kmh",
            "Velocidad promedio",
            N,
            min=5,
            max=90,
            unit="km/h",
            help="Entre 5 y 90 km/h.",
        ),  # fmt: skip
        FieldSpec(
            "operating_hours", "Horas operativas", N, min=0, exclusive_min=True, max=24, unit="h"
        ),
        FieldSpec("loading_h", "Cargue", N, min=0, max=24, unit="h"),
        FieldSpec("dock_wait_h", "Espera en muelle", N, min=0, max=24, unit="h"),
        FieldSpec("stops", "Número de paradas", INT, min=0, max=500),
        FieldSpec("minutes_per_stop", "Minutos por parada", N, min=0, max=600, unit="min"),
        FieldSpec("customer_wait_h", "Espera en cliente", N, min=0, max=24, unit="h"),
        FieldSpec("fill", "Llenado", P, min=0, exclusive_min=True, max=100, unit="%"),
        FieldSpec("backhaul", "Backhaul", P, min=0, max=100, unit="%"),
    ),
)

COMPATIBILITY = EntitySpec(
    name="compatibility",
    label="Compatibilidad ruta–vehículo",
    plural="Compatibilidades",
    description="Tipos de vehículo que pueden atender cada ruta (solo cuentan los listados).",
    key_fields=("corridor_code", "vehicle_type"),
    fields=(
        FieldSpec("corridor_code", "Ruta", FieldType.SELECT, options_from="corridors"),
        FieldSpec(
            "vehicle_type", "Tipo de vehículo", FieldType.SELECT, options_from="vehicle_types"
        ),
    ),
)

FLEET = EntitySpec(
    name="fleet",
    label="Flota propia actual",
    plural="Flota propia actual",
    description="Cuántos vehículos propios hay hoy por tipo (base de la brecha de capacidad).",
    key_fields=("vehicle_type",),
    fields=(
        FieldSpec(
            "vehicle_type", "Tipo de vehículo", FieldType.SELECT, options_from="vehicle_types"
        ),
        FieldSpec("count", "Cantidad", INT, min=0, max=10000),
    ),
)

DAILY_DEMAND = EntitySpec(
    name="daily_demand",
    label="Demanda diaria",
    plural="Demanda diaria",
    description=(
        "Toneladas por ruta y día. Un día sin fila es dato ausente, nunca cero: no se rellena."
    ),
    key_fields=("corridor_code", "date"),
    fields=(
        FieldSpec("corridor_code", "Ruta", FieldType.SELECT, options_from="corridors"),
        FieldSpec("date", "Fecha", FieldType.DATE),
        FieldSpec("tons", "Toneladas", N, min=0, max=100000, unit="t"),
    ),
)

CUSTOMER = EntitySpec(
    name="customer",
    label="Cliente",
    plural="Clientes",
    description="Punto de entrega con su ventana horaria. La ubicación debe estar en Colombia.",
    key_fields=("code",),
    fields=(
        FieldSpec("code", "Código", T, max_length=20, help="Único por empresa."),
        FieldSpec("name", "Nombre", T, max_length=80),
        FieldSpec("address", "Dirección", T, required=False, max_length=120),
        FieldSpec("lat", "Latitud", N, min=-4.3, max=13.5, help="Entre -4,3 y 13,5."),
        FieldSpec("lon", "Longitud", N, min=-82, max=-66, help="Entre -82 y -66."),
        FieldSpec(
            "service_minutes",
            "Minutos de servicio",
            N,
            min=0,
            exclusive_min=True,
            max=600,
            unit="min",
        ),  # fmt: skip
        FieldSpec("window_start", "Ventana desde", FieldType.TIME),
        FieldSpec(
            "window_end",
            "Ventana hasta",
            FieldType.TIME,
            help="Posterior a la inicial; no se aceptan ventanas que cruzan la medianoche.",
        ),  # fmt: skip
        FieldSpec("restrictions", "Restricciones", T, required=False, max_length=120),
    ),
)

VEHICLE = EntitySpec(
    name="vehicle",
    label="Vehículo",
    plural="Vehículos",
    description="Flota disponible para el ruteo diario: propios, reserva y terceros.",
    key_fields=("id",),
    fields=(
        FieldSpec("id", "Identificador", T, max_length=20),
        FieldSpec("plate", "Placa", T, max_length=30),
        FieldSpec(
            "vehicle_type", "Tipo de vehículo", FieldType.SELECT, options_from="vehicle_types"
        ),
        FieldSpec(
            "capacity_kg", "Capacidad (kg)", N, min=0, exclusive_min=True, max=100000, unit="kg"
        ),
        FieldSpec(
            "kind",
            "Condición",
            FieldType.SELECT,
            options=(("own", "Propio"), ("reserve", "Reserva"), ("third_party", "Tercero")),
        ),  # fmt: skip
        FieldSpec("gps_id", "Identificador GPS", T, required=False, max_length=30),
    ),
)

ORDER = EntitySpec(
    name="order",
    label="Pedido del día",
    plural="Pedidos del día",
    description="Pedidos que entran al plan de la mañana. Los cambios aplican al reiniciar el día.",
    key_fields=("id",),
    fields=(
        FieldSpec("id", "Identificador", T, max_length=20, help="No puede repetirse en el día."),
        FieldSpec("customer_code", "Cliente", FieldType.SELECT, options_from="customers"),
        FieldSpec("kg", "Peso (kg)", N, min=0, exclusive_min=True, max=100000, unit="kg"),
        FieldSpec("m3", "Volumen (m³)", N, min=0, max=1000, unit="m³"),
        FieldSpec("window_start", "Ventana desde", FieldType.TIME),
        FieldSpec("window_end", "Ventana hasta", FieldType.TIME),
        FieldSpec(
            "priority",
            "Prioridad",
            FieldType.SELECT,
            options=(("1", "1 · alta"), ("2", "2 · normal"), ("3", "3 · baja")),
        ),  # fmt: skip
    ),
)

ENTITIES: dict[str, EntitySpec] = {
    e.name: e
    for e in (VEHICLE_TYPE, CORRIDOR, COMPATIBILITY, FLEET, DAILY_DEMAND, CUSTOMER, VEHICLE, ORDER)
}


@dataclass(frozen=True)
class ParameterSpec:
    """Parámetro con vigencia: cada cambio crea una versión, nunca se sobrescribe la anterior."""

    key: str
    area: str  # capacidad | ruteo
    field: FieldSpec
    help: str = ""

    @property
    def label(self) -> str:
        return self.field.label


def _p(key: str, area: str, field: FieldSpec, help_: str = "") -> ParameterSpec:
    return ParameterSpec(key, area, field, help_)


PARAMETERS: dict[str, ParameterSpec] = {
    p.key: p
    for p in (
        _p(
            "design_percentile",
            "capacidad",
            FieldSpec("design_percentile", "Percentil de diseño", P, min=50, max=99.9, unit="%"),
            "Percentil de la demanda histórica con el que se dimensiona la flota.",
        ),  # fmt: skip
        _p(
            "reserve",
            "capacidad",
            FieldSpec("reserve", "Reserva de flota", P, min=0, max=50, unit="%"),
        ),
        _p(
            "days_per_month",
            "capacidad",
            FieldSpec("days_per_month", "Días operativos por mes", INT, min=1, max=31, unit="días"),
        ),  # fmt: skip
        _p(
            "window_days",
            "capacidad",
            FieldSpec("window_days", "Ventana de demanda", INT, min=7, max=365, unit="días"),
            "Días calendario que se miran hacia atrás para calcular la demanda de diseño.",
        ),  # fmt: skip
        _p(
            "oee_availability",
            "capacidad",
            FieldSpec(
                "oee_availability",
                "OEE · disponibilidad",
                P,
                min=0,
                exclusive_min=True,
                max=100,
                unit="%",
            ),
        ),  # fmt: skip
        _p(
            "oee_utilization",
            "capacidad",
            FieldSpec(
                "oee_utilization",
                "OEE · utilización",
                P,
                min=0,
                exclusive_min=True,
                max=100,
                unit="%",
            ),
        ),  # fmt: skip
        _p(
            "oee_performance",
            "capacidad",
            FieldSpec(
                "oee_performance",
                "OEE · rendimiento",
                P,
                min=0,
                exclusive_min=True,
                max=100,
                unit="%",
            ),
        ),  # fmt: skip
        _p(
            "max_fill",
            "ruteo",
            FieldSpec("max_fill", "Llenado máximo del vehículo", P, min=10, max=100, unit="%"),
            "Capacidad operativa = capacidad × llenado máximo.",
        ),  # fmt: skip
        _p(
            "service_kg_per_min",
            "ruteo",
            FieldSpec(
                "service_kg_per_min",
                "kg por minuto de servicio",
                N,
                min=0,
                exclusive_min=True,
                max=1000,
                unit="kg/min",
            ),  # fmt: skip
            "Servicio = minutos del cliente + kg / este valor.",
        ),
        _p(
            "weight_travel",
            "ruteo",
            FieldSpec("weight_travel", "Peso del viaje", N, min=0, max=1000),
        ),
        _p(
            "weight_wait",
            "ruteo",
            FieldSpec("weight_wait", "Peso de la espera", N, min=0, max=1000),
        ),
        _p(
            "weight_delay",
            "ruteo",
            FieldSpec("weight_delay", "Peso del retraso", N, min=0, max=1000),
        ),
        _p(
            "weight_overtime",
            "ruteo",
            FieldSpec("weight_overtime", "Peso de horas extra", N, min=0, max=1000),
        ),
        _p(
            "transshipment_min",
            "ruteo",
            FieldSpec("transshipment_min", "Transbordo ante avería", N, min=0, max=240, unit="min"),
        ),  # fmt: skip
        _p(
            "reload_min",
            "ruteo",
            FieldSpec("reload_min", "Recarga en el CEDI", N, min=0, max=240, unit="min"),
        ),
        _p(
            "reserve_activation_cost",
            "ruteo",
            FieldSpec(
                "reserve_activation_cost",
                "Costo de activar reserva",
                N,
                min=0,
                max=10000,
                unit="puntos",
            ),
        ),  # fmt: skip
        _p(
            "risk_margin_min",
            "ruteo",
            FieldSpec("risk_margin_min", "Holgura que marca riesgo", N, min=0, max=120, unit="min"),
        ),
        _p("departure", "ruteo", FieldSpec("departure", "Hora de salida", FieldType.TIME)),
        _p("shift_end", "ruteo", FieldSpec("shift_end", "Fin de turno", FieldType.TIME)),
    )
}
