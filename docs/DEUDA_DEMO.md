# Deuda de la demo (elementos DEMO-ONLY)

Todo lo listado está aislado detrás de un puerto y marcado `DEMO-ONLY` en el código. Ninguno debe
presentarse como capacidad productiva. Última actualización: 2026-10-14.

| Elemento | Ubicación | Puerto que lo abstrae | Cómo sustituirlo |
|---|---|---|---|
| Datos sintéticos de capacidad (maestros, demanda de 75 días con semilla, escenarios) y perfiles por empresa (A, B y derivados del slug) | `adapters/outbound/demo_data/` | `CapacityInputsReader` | Lector real de maestros, parámetros con vigencia y demanda desde la base/CSV validado |
| Repositorio de resultados de capacidad en memoria | `adapters/outbound/persistence_memory/capacity_results.py` | `CapacityResultWriter` / `CapacityResultReader` | Adaptador SQLAlchemy sobre la tabla `capacity_result` del tenant autenticado |
| Registro de tenants, usuarios, refresh tokens, auditoría, límite de tasa y proveedor de espacios de trabajo en memoria | `adapters/outbound/persistence_memory/control_plane.py` | `TenantRegistryPort`, `UserRepositoryPort`, `RefreshTokenStorePort`, `AuditLogPort`, `RateLimiterPort`, `TenantWorkspaceProvider` | Adaptadores sobre `pg-control` (registro, usuarios, auditoría), Redis (límite de tasa, revocaciones) y una conexión por tenant |
| Persistencia SQL (descrita y **comentada**) | `adapters/outbound/persistence_sql/__init__.py` | (idem) | Implementarla, con migraciones Alembic `control_plane` y `tenant` |
| `docker-compose` con `pg-control`, `pg-tenant-a`, `pg-tenant-b`, Redis (**comentado**) | `infra/docker-compose.yml` | — | Descomentar, definir secretos en `.env`, validar con Docker |
| Clave de firma JWT efímera en `local`; contraseñas sembradas aleatorias impresas en consola | `bootstrap/settings.py`, `bootstrap/application.py::seed_demo` | `TokenServicePort` | Secretos en un gestor (`SecretsPort`), usuarios reales y flujo de alta/recuperación |
| Composición con adaptadores demo | `bootstrap/` | — | Segundo contenedor de composición para producción |
| Datos sintéticos de ruteo (CEDI Funza; Empresa A: 36 clientes y 4 turbos + reserva + tercero; B distinta) | `adapters/outbound/demo_data/routing_dataset.py` | `RoutingInputsReader` | Lector de clientes, pedidos y vehículos desde la base o CSV validado |
| Proveedor de tiempos simulado (Haversine × 1,35, congestión inventada por hora, falla a pedido) y respaldo por perfil de velocidades | `adapters/outbound/traffic/simulated.py` | `TrafficTimePort`, `FallbackTravelTimePort`, `TrafficProviderControl` | Adaptador de un proveedor real de rutas; el respaldo se conserva |
| Reloj acelerado por empresa (pausa, velocidad, avance) | `adapters/outbound/clock/simulated.py` | `SimulationClockPort` | Reloj real; el GPS real reemplaza la posición simulada |
| Estado del día operativo en memoria (planes, eventos, propuestas, cierres) | `adapters/outbound/persistence_memory/routing_state.py` | `RoutingRepositoryPort` | Adaptador SQL sobre `route_plan`, `plan_stop`, `event` del tenant |
| Simulador de GPS (lecturas cada 2 min simulados, posición en línea recta según el plan, corte de señal a pedido) | `adapters/outbound/gps/simulated.py`, `application/use_cases/routing/gps_support.py` | `GpsPort`, `GpsSimulationControl` | Adaptador del proveedor de GPS real; el control de corte de señal desaparece |
| Seguimiento programado y SSE dentro del proceso de la API (un solo proceso) | `adapters/inbound/http/app.py`, `routes_routing.py` | `TenantWorkspaceCatalog` | Scheduler/worker externo y bus de eventos (Redis) para varios procesos |
| Exportación CSV rápida generada en el navegador (tablero y hoja del conductor); el Excel ya se genera en el servidor | `APP/Frontend/src/domain-ui/csv.ts` | — | Unificar en la exportación del servidor, auditada |
| Almacén de maestros, parámetros e historial en memoria (se pierde al reiniciar) | `adapters/outbound/persistence_memory/master_data.py` | `MasterDataStorePort` | Adaptador SQL: una tabla por maestro en la base del tenant, `parameter_version` y `change_history` |
| Generador de historia sintética para ML (90 días, patrones sembrados, semilla por empresa) | `adapters/outbound/demo_data/ml_history.py` | `HistoryReaderPort` | Lector de historia real (entregas, esperas, tráfico) desde la base del tenant |
| Registro de modelos en memoria (artefactos `pickle` con SHA-256) | `adapters/outbound/persistence_memory/ml_registry.py`, `adapters/outbound/ml/codec.py` | `ModelRegistryPort` | Almacenamiento por tenant (tabla `model_registry` + objeto/archivo aislado), formato sin ejecución de código (`skops`/ONNX) y firma del registro |
| Contraseña compartida de demostración por variable de entorno (`DEMO_PASSWORD`) | `bootstrap/settings.py`, `bootstrap/application.py::seed_demo` | `PasswordHasherPort` | Usuarios reales con alta/recuperación, contraseñas individuales y MFA |
| Interfaz servida por la propia API en un solo proceso | `adapters/inbound/http/app.py::_mount_frontend` | — | Servidor web/CDN estático delante de la API y varias réplicas con estado externo (PostgreSQL/Redis) |
| Exportador de hojas de cálculo (openpyxl) | `adapters/outbound/export/spreadsheets.py` | `SpreadsheetExporterPort` | Mantener; añadir generación en segundo plano para volúmenes grandes |

## Supuestos abiertos que afectan resultados
- Volumen nuevo en la proyección (D-007): aceptado para la demo; validar con negocio antes de usar
  datos reales.
- OTIF (D-013/D-025): los escenarios son simulaciones con datos sintéticos; las entregas
  incompletas son un parámetro de ejemplo. No son una medición.
- Los valores del dataset sintético (capacidades, tarifas, demanda) son inventados y **no
  corresponden a ninguna empresa ni reproducen las cifras de referencia** de `DOCS.MD` §10.

## Aún no existe (se agregará con su fase)
generador de datos
de ML, SSE/WebSocket, proxy con TLS, MFA (fuera del alcance de la demo).
