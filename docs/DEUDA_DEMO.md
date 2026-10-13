# Deuda de la demo (elementos DEMO-ONLY)

Todo lo listado está aislado detrás de un puerto y marcado `DEMO-ONLY` en el código. Ninguno debe
presentarse como capacidad productiva. Última actualización: 2026-10-13.

| Elemento | Ubicación | Puerto que lo abstrae | Cómo sustituirlo |
|---|---|---|---|
| Datos sintéticos de capacidad (maestros, demanda de 75 días con semilla, escenarios) y perfiles por empresa (A, B y derivados del slug) | `adapters/outbound/demo_data/` | `CapacityInputsReader` | Lector real de maestros, parámetros con vigencia y demanda desde la base/CSV validado |
| Repositorio de resultados de capacidad en memoria | `adapters/outbound/persistence_memory/capacity_results.py` | `CapacityResultWriter` / `CapacityResultReader` | Adaptador SQLAlchemy sobre la tabla `capacity_result` del tenant autenticado |
| Registro de tenants, usuarios, refresh tokens, auditoría, límite de tasa y proveedor de espacios de trabajo en memoria | `adapters/outbound/persistence_memory/control_plane.py` | `TenantRegistryPort`, `UserRepositoryPort`, `RefreshTokenStorePort`, `AuditLogPort`, `RateLimiterPort`, `TenantWorkspaceProvider` | Adaptadores sobre `pg-control` (registro, usuarios, auditoría), Redis (límite de tasa, revocaciones) y una conexión por tenant |
| Persistencia SQL (descrita y **comentada**) | `adapters/outbound/persistence_sql/__init__.py` | (idem) | Implementarla, con migraciones Alembic `control_plane` y `tenant` |
| `docker-compose` con `pg-control`, `pg-tenant-a`, `pg-tenant-b`, Redis (**comentado**) | `infra/docker-compose.yml` | — | Descomentar, definir secretos en `.env`, validar con Docker |
| Clave de firma JWT efímera en `local`; contraseñas sembradas aleatorias impresas en consola | `bootstrap/settings.py`, `bootstrap/application.py::seed_demo` | `TokenServicePort` | Secretos en un gestor (`SecretsPort`), usuarios reales y flujo de alta/recuperación |
| Composición con adaptadores demo | `bootstrap/` | — | Segundo contenedor de composición para producción |
| Exportación CSV generada en el navegador | `APP/Frontend/src/domain-ui/csv.ts` | — | Exportación en el servidor (Excel nativo), auditada |

## Supuestos abiertos que afectan resultados
- Volumen nuevo en la proyección (D-007): aceptado para la demo; validar con negocio antes de usar
  datos reales.
- OTIF (D-013): se mostrarán escenarios de ejemplo; son ilustrativos, no una medición.
- Los valores del dataset sintético (capacidades, tarifas, demanda) son inventados y **no
  corresponden a ninguna empresa ni reproducen las cifras de referencia** de `DOCS.MD` §10.

## Aún no existe (se agregará con su fase)
Simulador GPS, proveedor de tráfico simulado, `GpsPort`, `TrafficTimePort`, generador de datos
de ML, SSE/WebSocket, proxy con TLS, MFA (fuera del alcance de la demo).
