# Especificaciones técnicas de backend

Este documento complementa `DOCS.MD`. Si se detecta un conflicto que cambie el comportamiento, la seguridad o el alcance, debe registrarse y resolverse antes de implementarlo.

## 1. Ubicación y stack

Todo el backend vive en `APP/Backend/`. Stack previsto: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL 16 + PostGIS, Redis, OR-Tools, PuLP, NumPy, Pandas y scikit-learn. Calidad: pytest, pytest-cov, Ruff, mypy estricto en dominio/aplicación, import-linter, Bandit y pip-audit.

Estructura base:

```text
APP/Backend/
├── src/<package_name>/
│   ├── domain/
│   │   ├── shared/
│   │   ├── capacity/
│   │   ├── routing/
│   │   ├── tenancy/
│   │   └── patterns/
│   ├── application/
│   │   ├── ports/inbound/
│   │   ├── ports/outbound/
│   │   ├── use_cases/
│   │   └── dto/
│   ├── adapters/
│   │   ├── inbound/http/
│   │   ├── inbound/scheduler/
│   │   ├── inbound/cli/
│   │   ├── inbound/websocket/
│   │   └── outbound/
│   └── bootstrap/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── security/
│   ├── architecture/
│   └── ml/
├── alembic/
└── pyproject.toml
```

Seleccionar un nombre genérico para `<package_name>` y documentarlo. No utilizar el nombre de un cliente de demostración en el nombre técnico del paquete.

## 2. Arquitectura hexagonal y límites de capas

### Dominio

Contiene entidades, value objects, reglas de negocio, invariantes, servicios de dominio y errores. Ejemplos de objetos compartidos: `GeoPoint`, `TimeWindow`, `Money`, `Percentage`, `TenantId` y tipos propios para `Forecast`, `Anomaly`, `DelayRisk` y `Segment`.

El dominio no importa FastAPI, Pydantic para transporte HTTP, SQLAlchemy, Redis, scikit-learn, OR-Tools directamente salvo que se apruebe y justifique una excepción específica, ni ningún adaptador. La integración con un solver complejo debe ocultarse detrás de un puerto para que el dominio conserve sus reglas e invariantes independientes.

### Aplicación

Contiene casos de uso y define puertos inbound/outbound. Los casos de uso reciben dependencias por constructor y orquestan el dominio. Casos de uso iniciales, según corresponda al plan aprobado: `RunCapacityAnalysis`, `ProjectFiveYears`, `SimulateMonteCarlo`, `OptimizeFleetMix`, `BuildMorningPlan`, `HandleEvent`, `ApproveReroute`, `TrackFleet`, `TrainModels`, `DetectPatterns`, `LoadCsv` y `ProvisionTenant`.

No importa implementaciones de adaptadores. Los DTO de aplicación no deben ser modelos ORM.

### Adaptadores de entrada

- HTTP: routers, esquemas de petición/respuesta, autenticación/autorización y traducción de errores.
- Scheduler: corridas nocturnas, seguimiento, actualización de modelos y reentrenamiento.
- CLI: aprovisionar tenant, generar datos sintéticos, seed, migrar y entrenar.
- WebSocket/SSE: posiciones, estados y alertas autenticados con contexto de tenant.

### Adaptadores de salida

- Persistencia SQLAlchemy y mapeos dominio-ORM.
- Registro central de tenants y gestor de conexiones de bases cliente.
- GPS simulado detrás de `GpsPort` (`DEMO-ONLY`).
- Perfil de velocidad/Haversine detrás de `TrafficTimePort` (`DEMO-ONLY`).
- Stub de proveedor de tráfico para probar indisponibilidad (`DEMO-ONLY`).
- Modelos scikit-learn detrás de puertos ML.
- Seguridad: hash de contraseñas, JWT, secretos y auditoría.
- Caché Redis.
- Adaptadores de optimización OR-Tools/PuLP a través de puertos definidos.

`bootstrap` es el único lugar que importa las implementaciones concretas para realizar la composición de dependencias. Los adaptadores de salida no se importan entre sí.

## 3. Diseño del dominio

- Modela invariantes de forma explícita y con mensajes de error entendibles.
- Evita tipos primitivos ambiguos cuando un value object pueda hacer cumplir una regla (por ejemplo porcentajes, ventanas horarias o coordenadas).
- Los métodos de cálculo que puedan ser funciones puras deben ser deterministas y fáciles de probar.
- Define unidades para toneladas, kg, km, horas y minutos; no mezcles unidades sin conversión explícita.
- Las fechas/horas deben usar zona horaria bien definida y evitar comparar datetimes naïve con aware. La hora operacional de la demo corresponde a Bogotá.
- No conviertas datos ausentes en ceros sin una regla explícita.
- En optimizadores distingue resultados óptimos, factibles, inviables, con timeout y con error.

## 4. Puerto y contratos

Diseñar interfaces pequeñas y específicas. Puertos de salida previstos incluyen, como mínimo cuando sean necesarios: repositorios de vehículos, pedidos, clientes, rutas, eventos, planes y resultados; `GpsPort`, `TrafficTimePort`, `GeocodingPort`, `ClockPort`, `DemandForecaster`, `AnomalyDetector`, `DelayRiskPredictor`, `PatternMiner`, `SecretsPort`, `AuditLogPort`, `TenantRegistryPort`, `TenantConnectionPort`, `PasswordHasherPort`, `TokenServicePort`, `CachePort` y `EventBusPort`.

Separar lectura/escritura cuando los consumidores necesiten permisos o contratos distintos. Cada puerto crítico debe tener una suite de pruebas de contrato reutilizable para adaptadores simulados y futuros adaptadores reales.

## 5. Casos de uso principales

- Capacidad: cálculo P1–P9 según `DOCS.MD`; persistir método, versión de algoritmo, fecha, entradas y parámetros efectivos para poder explicar el resultado.
- Ruteo: plan de mañana, seguimiento, evaluación del riesgo, manejo de eventos, aprobación/rechazo y versionado inmutable.
- ML: generar dataset, entrenar, registrar versión/hash/metrics, comprobar integridad antes de cargar, predecir y detectar patrones por tenant.
- Tenancy: resolver tenant autenticado, provisionar, suspender, migrar y obtener conexiones aisladas.
- Imports/exports: validar archivos por esquema y tamaño; neutralizar fórmulas al exportar planillas.

Los casos de uso no deben conocer si un evento viene de una petición HTTP, del simulador o de un scheduler.

## 6. Multi-tenancy y base de datos

La demo tendrá tres instancias PostgreSQL en Docker Compose:

- `pg-control`: catálogo central con slug, estado, metadatos y configuración cifrada de conexión.
- `pg-tenant-a`: datos aislados de Empresa Demo A.
- `pg-tenant-b`: datos aislados de Empresa Demo B.

Cada tenant tiene base independiente. En despliegues productivos cada configuración puede apuntar a otro host/servidor. El demo con tres contenedores no debe describirse como tres servidores físicos.

Requisitos:

- El claim del tenant procede de token firmado y validado. Un `tenant_id` recibido en el body, query o header no puede seleccionar la base.
- La conexión/sesión se obtiene ligada al tenant ya autenticado y autorizado. Los repositorios de tenant no aceptan identificador libre del tenant para decidir conexión.
- Los pools se limitan por tenant y se cierran de manera ordenada. Manejar errores de conexión sin usar silenciosamente otra base.
- Los trabajos programados, WebSocket/SSE, exportaciones, caché y modelos ML preservan aislamiento.
- Secretos cifrados autenticadamente, clave externa a Git y configuración que falle de forma segura si falta la clave. No loguear DSN ni credenciales.
- Migraciones separadas para `control_plane` y `tenant`; comandos individuales y globales con resultados por tenant.
- `ProvisionTenant` debe ser idempotente o definir compensación ante fallos parciales.
- Al suspender un tenant, se bloquean nuevas solicitudes y trabajos según una política explícita, sin filtrar si existe otro tenant.

Pruebas de aislamiento obligatorias: acceso cruzado mediante ID manipulado, token de otro tenant, operaciones paralelas, suspensión, caché, streams, archivos de ML y exportaciones.

## 7. Persistencia, transacciones y versionado

- Las entidades ORM no son entidades de dominio. Crear mapeos en adaptadores de persistencia.
- Definir límites transaccionales de casos de uso y estrategia ante fallos parciales, especialmente al aprobar un re-ruteo o aprovisionar un tenant.
- Cada recálculo de rutas crea una nueva versión con motivo, actor, fecha, eventos aplicados y relación con el plan previo. Las versiones pasadas son inmutables.
- Parámetros y configuración relevante conservan historial de valor previo y vigencia. Evitar actualización destructiva.
- `gps_position` puede tener volumen alto; documentar índices, estrategia de retención y archivado. No añadir auditoría redundante que haga inviable la escritura, siempre que las excepciones mantengan trazabilidad documentada.
- Añadir índices según patrones de consulta y claves foráneas/constraints. La integridad no debe depender solo de validaciones de frontend.

## 8. Contratos de API

Diseñar una API coherente, versionada si la amplitud lo justifica y documentada en español. Evitar publicar información sensible en esquemas o errores. Los modelos Pydantic deben validar tipo, rango, longitud y valores permitidos.

Agrupar endpoints por capacidad: autenticación/perfil, tenants (solo super-admin), maestros/CSV/parámetros, capacidad y resultados, órdenes/planes/paradas, eventos y propuestas, GPS/estado, patrones ML, hoja de ruta/confirmación y métricas. No se prescribe una lista rígida de URL; definirla en el plan técnico para evitar duplicados.

- Errores con código estable y mensaje en español, sin stack trace ni secretos.
- Paginación/filtros y límites para listas grandes.
- Rate limit por usuario y tenant en login, eventos y operaciones costosas.
- Permisos verificados en cada operación, no solo en la UI.
- WebSocket/SSE autenticado y autorizado por tenant y rol; no enviar eventos de otra empresa.
- Operaciones de alto impacto generan una propuesta persistida para aprobación y no aplican cambios prematuramente.

## 9. Algoritmos de capacidad

Implementar P1–P9 tal como se especifica en `DOCS.MD`, con especial atención a:

- Datos de demanda ausentes como ausentes, no ceros.
- Porcentajes normalizados a fracción y unidades explícitas.
- Redondeo de flota documentado y probado.
- Monte Carlo reproducible con semilla y distribuciones que no generen capacidad ni ciclo negativos.
- Optimización MIP con compatibilidad, límites de tiempo y estados del solver.
- P8 no debe tener un límite fijo de 40 vehículos: el espacio de búsqueda se deriva del problema y contempla tipos de vehículo y su costo/capacidad.
- Ningún criterio de aceptación se satisface introduciendo resultados constantes en producción o ajustando fórmulas a la fuerza.

## 10. Ruteo y eventos

- Encapsular Haversine × 1,35, perfil de velocidad y simulador en adaptadores `DEMO-ONLY`.
- El dominio calcula llegadas, ventanas, espera, carga, retrasos y puntaje con unidades verificadas.
- Usar OR-Tools detrás de puerto/adaptador y mantener la heurística de comparación solicitada.
- Descartar planes que violen capacidad. Marcar órdenes sin asignar con causa.
- El cambio de plan crea versión nueva. Aplicar las reglas de consentimiento del despachador y la restricción de no cambiar una carga de vehículo salvo transbordo o recarga en CEDI.
- Si el proveedor de tráfico no responde, usar `speed_profile`, comunicar que no hay tráfico en vivo y continuar si los datos disponibles permiten hacerlo.
- GPS sin señal después de 15 minutos: mantener plan, alertar y presentar timestamp/edad de la última posición.

## 11. Machine learning

Modelos aislados por tenant con semillas reproducibles, registro de versión y hash del artefacto. Verificar integridad antes de cargar artefactos. No entrenar modelos de un tenant con datos de otro, ni siquiera indirectamente mediante features compartidas no autorizadas.

- Demanda: gradient boosting/quantile regression, comparación temporal contra línea base estacional, MAE y MAPE con manejo de ceros.
- Anomalías: Isolation Forest sobre servicio/espera; explicaciones orientativas, no causales.
- Riesgo: clasificador como HistGradientBoosting, métricas precision/recall/AUC/Brier y calibración.
- Segmentación: KMeans o DBSCAN, características descritas y etiquetas legibles.
- Usar partición temporal para evitar leakage. Registrar fecha, features, versión, métricas, semilla y descripción de datos.
- `tests/ml` verifica el comportamiento en fixtures conocidos; no afirmar rendimiento general a partir de datos sintéticos.

## 12. Seguridad

Implementar y probar los controles de `DOCS.MD` por categoría OWASP 2021. Los controles críticos incluyen RBAC y autorización de objetos, Argon2id, JWT/rotación/revocación donde implementado, cifrado de secretos, consultas parametrizadas, validación de imports, cabeceras de seguridad, CORS restrictivo, no-root, dependencias auditadas, logs seguros, rate limiting, protección SSRF y aislamiento de tenants.

Ejecutar y reportar resultados reales de Ruff, mypy, import-linter, pytest/coverage, Bandit, pip-audit, npm audit y escaneo de secretos. Un comando que no se pudo ejecutar debe quedar como no verificado, nunca como aprobado. Mantener `docs/SEGURIDAD_OWASP.md`, `docs/MODELO_AMENAZAS.md` y `docs/PRIVACIDAD.md` actualizados con evidencia de archivo/prueba.

## 13. Datos sintéticos, simulación y reloj

- Semilla fija y datos visibles como demostración.
- `GpsPort` tiene una implementación simulada marcada `DEMO-ONLY`, controlable por reloj acelerado.
- `ClockPort` permite inyectar reloj real/simulado y evitar esperas reales en pruebas.
- El stub de proveedor permite probar tanto respuesta como fallo.
- Las contraseñas seed se generan aleatoriamente, se muestran una sola vez en consola y nunca se incorporan al repo.
- Los datos generados deben respetar constraints de dominio y producir escenarios repetibles de eventos y patrones ML.

## 14. Pruebas obligatorias

- Unitarias para value objects, invariantes y fórmulas de dominio.
- Casos de uso con puertos falsos/mocks y verificación de orquestación.
- Integración contra PostgreSQL/PostGIS y Redis reales de contenedor.
- Pruebas de contrato por puerto y por adaptador.
- Pruebas de arquitectura para cada regla de dependencia.
- Pruebas security para permisos, objetos, tenant, imports, SSRF, headers, autenticación, auditoría y secretos.
- Pruebas multi-tenant concurrentes y de aislamiento completo.
- Pruebas ML deterministas y sin fuga temporal/entre tenants.
- Pruebas del solver para problema factible, inviable y límite de tiempo.
- Cobertura de dominio >= 90 %; informar denominador, reporte y exclusiones reales.

## 15. Definición de terminado del backend

Un incremento se considera terminado solo si hay implementación, prueba relacionada, mapeo de errores y documentación pertinente. La versión de demo se considera lista únicamente si los comandos documentados se ejecutan en el entorno disponible, se completa el flujo end-to-end y el informe separa claramente lo implementado, probado, parcial y pendiente. Nunca atribuir capacidades productivas a adaptadores simulados.
