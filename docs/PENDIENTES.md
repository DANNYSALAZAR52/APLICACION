# Pendientes y hoja de ruta

Última actualización: 2026-10-13 (cierre de la sesión 2). Complementa
`docs/ESTADO_IMPLEMENTACION.md` (qué está hecho) y `docs/REGISTRO_DEMO.md` (bitácora).

## 1. Qué se avanzó (resumen)

| Fase | Resultado |
|---|---|
| 0 | Esqueleto hexagonal, reglas de arquitectura verificadas (import-linter + pruebas AST), infraestructura comentada |
| 1 | Capacidad de flota P1–P9 con casos de uso, solver OR-Tools, CLI y 98 % de cobertura del dominio |
| 2 | Multi-tenancy en memoria, Argon2id, JWT + refresh rotatorio, RBAC de 5 roles, auditoría, API HTTP endurecida |
| 6 (parcial) | Frontend: login, tablero de capacidad, administración de empresas, auditoría |

Cifras de calidad: backend 288 pruebas, frontend 79 pruebas, todos los linters/auditorías limpios
(ver `ESTADO_IMPLEMENTACION.md`).

## 2. Lo que falta, por fase

### Fase 3 — Ruteo dinámico (el siguiente paso recomendado)
**Backend:** value objects `GeoPoint`/`TimeWindow`; adaptador de tiempos Haversine × 1,35 con perfil
de velocidad y factor de cierre (`TrafficTimePort`, DEMO-ONLY) y stub de proveedor con fallo
simulado; cálculo de llegadas, esperas, retrasos, carga y puntaje del plan; plan de la mañana con
OR-Tools (VRP con ventanas y capacidad) **y** heurística de inserción por arrepentimiento + 2-opt +
reubicación como comparación; versionado inmutable del plan; casos de uso `BuildMorningPlan`,
`HandleEvent`, `ApproveReroute`, `TrackFleet`; eventos (cierre, pedido urgente, cambio de ventana,
avería); regla de no cambiar carga de vehículo salvo transbordo/recarga; propuestas persistidas que
solo se aplican con aprobación del despachador; validaciones de clientes/ventanas (criterio 11);
indicadores diarios con **escenarios de OTIF de ejemplo** (100 %, 90 %, ...; D-013); comparación plan
estático vs. dinámico con mismos pedidos y denominadores.
**Frontend:** torre de control con mapa (Leaflet + OpenStreetMap, atribución y límites de tiles),
línea de tiempo por vehículo, registro de eventos y aprobación/rechazo con confirmación, hoja de
ruta del conductor mobile-first con enlace de Google Maps (formato `maps/dir/?api=1`, máx. de
paradas), indicadores diarios.
**Dependencias nuevas a aprobar:** `leaflet` (+ tipos) en el frontend.
**Criterios de aceptación:** 11 (cliente con latitud 40 y ventana 14:00–10:00 se rechaza con
explicación) y 12 (si falla el proveedor de tiempos se usa `speed_profile` y se avisa "Tiempos
estimados sin tráfico").

### Fase 4 — Datos sintéticos y machine learning
Generador determinista (60–90 días, ~15 corredores, 40–300 clientes por tenant, patrones
sembrados); cuatro modelos detrás de puertos (`DemandForecaster`, `AnomalyDetector`,
`DelayRiskPredictor`, `PatternMiner`) con scikit-learn; partición temporal; registro de versión,
métricas y hash del artefacto con verificación antes de cargar; entrenamiento aislado por tenant;
pantalla "Patrones detectados" con aviso de datos sintéticos; comparación ML vs. percentil
histórico en el tablero de capacidad (hoy "No disponible"). **Dependencia nueva:** `scikit-learn`.

### Fase 5 — Simulación GPS y tiempo real
`GpsPort` simulado (DEMO-ONLY) con reloj acelerado y pausa/reinicio, geocerca de 100 m > 5 min,
alerta de "sin señal" a los 15 min, SSE/WebSocket autenticado y con contexto de tenant, tarea
programada de seguimiento, `ClockPort` simulado en la interfaz.

### Fase 6 — Resto del frontend
Maestros y parámetros (CRUD, importación CSV con previsualización y validación, historial con
vigencia), exportación a Excel (`.xlsx`) generada en el servidor, estados de pantalla completos para
las vistas nuevas, revisión visual y responsive de todas las pantallas.

### Fase 7 — Seguridad, documentación y cierre
- Documentos requeridos por `DOCS.MD` §16 que **aún no existen**: `SEGURIDAD_OWASP.md`,
  `MODELO_AMENAZAS.md` (STRIDE: login, carga CSV, eventos, GPS, aprovisionamiento),
  `PRIVACIDAD.md`, `ARQUITECTURA.md` (con matriz SOLID–evidencia), `MULTITENANT.md`, `ML.md`,
  `DEMO_GUION.md`, `GLOSARIO.md`, `ROADMAP.md` (ver §4).
- Escaneo de secretos (herramienta no instalada), SBOM, CI local, proxy inverso con TLS de
  desarrollo, pruebas E2E con navegador (Playwright) del guion completo, medición de cobertura
  del frontend, pruebas de accesibilidad automatizadas.
- Reporte final que separe implementado / probado / parcial / pendiente / DEMO-ONLY.

## 3. Deuda transversal conocida

| Tema | Detalle |
|---|---|
| Revisión visual | La interfaz nunca se vio en un navegador durante el desarrollo; revisar diseño, responsive y gráficos |
| `scripts/start-demo.ps1` | Solo se validó la sintaxis; no se lanzó |
| Base de datos | Comentada a propósito (D-001): PostgreSQL/PostGIS ×3, Redis, Alembic `control_plane`/`tenant`, `ProvisionTenant` con BD real, `SecretsPort` con cifrado de conexiones, pruebas de integración y aislamiento reales |
| Persistencia de la demo | Todo en memoria: reiniciar borra sesiones, empresas creadas, auditoría y cambia las contraseñas (D-018) |
| Límite de tiempo del solver | Solo probado el mapeo de estados con dobles; falta una prueba con timeout real |
| Python | Solo probado en 3.13; la especificación pide 3.12 |
| `Makefile` | Sin probar (no hay `make`); `make up`/`make seed` no existen |
| Criterios de aceptación 1–10 | No verificables sin la planilla original `Capacidad_Flota_Transportes_VIGIA.xlsx` ni el HTML "Ruteo dinámico VIGIA" |
| Aislamiento multi-tenant | Lógico en memoria, un solo proceso (D-017); falta la demostración con tres PostgreSQL |
| Auditoría | Cubre login, tablero y empresas; faltan cambios de maestros/parámetros con valor anterior y vigencia |
| Exportación | CSV generado en el navegador (D-019); pasar a servidor con auditoría |

## 4. Hoja de ruta de la demo al producto (`DOCS.MD` §16)

1. Adaptadores reales para GPS y proveedores de rutas, geocodificación y optimización.
2. Integración con ERP/TMS/CRM por API.
3. Endurecimiento de seguridad: MFA, pruebas de penetración externas, rotación de secretos, cifrado
   en reposo (incluida la ubicación).
4. Operación multi-tenant a escala: aprovisionamiento automatizado, respaldos, observabilidad por
   tenant y límites por plan.
5. Facturación por suscripción y licenciamiento por vehículo.
6. Mejora de modelos de ML con datos reales y evaluación operacional.

## 5. Decisiones de negocio todavía abiertas

| Id | Tema | Estado |
|---|---|---|
| D-007 | Interpretación del "volumen nuevo" en la proyección | Aceptada para la demo; **validar con negocio** antes de usar datos reales |
| D-013 | Definición de puntualidad vs. OTIF y denominadores | Para la demo, escenarios de ejemplo; definir con negocio para producción |
| — | Ventanas que cruzan medianoche (`DOCS.MD` §8) | No decidido: hoy no se aceptan implícitamente |
| — | Clasificación legal de los datos de ubicación GPS | Pendiente de revisión jurídica (`PRIVACIDAD.md`) |
| — | Costo variable y de terceros por tipo/corredor | Supuestos sintéticos; reemplazar con datos de finanzas |

## 6. Riesgos

- Sin la planilla original no se puede demostrar fidelidad con el prototipo.
- La demo vive en un solo proceso y en memoria: no demuestra escalabilidad ni persistencia.
- Sin revisión visual ni E2E, errores de interfaz pueden pasar desapercibidos hasta la primera
  presentación.
- El alcance restante (ruteo, ML, tiempo real, ~6 pantallas) es grande: conviene avanzar por fases
  verticales con aprobación en cada una.

## 7. Cómo retomar

0. **Subir a GitHub (pendiente):** el commit local existe pero el `push` no se completó (requiere
   que el usuario autorice en el navegador). En una terminal PowerShell propia, desde la carpeta
   `DEMO`, con el repositorio privado `DANNY5SALAZAR/fleetplanner-demo` ya creado y vacío:

   ```powershell
   $git = "$env:LOCALAPPDATA\fleetplanner-tools\git"
   $env:Path = "$git\cmd;$git\mingw64\bin;$git\ucrt64\bin;$env:Path"
   git push -u origin main      # se abre el navegador para autorizar con su cuenta de GitHub
   ```
   Si ya tiene Git instalado en el sistema, basta `git push -u origin main`.
1. Leer `README.md` (puesta en marcha) y este archivo.
2. Ejecutar `scripts\setup-frontend.ps1` y `scripts\start-demo.ps1`; revisar la interfaz en el navegador.
3. Aprobar la fase 3 (y la dependencia `leaflet`) o indicar ajustes a lo ya hecho.
4. Cada incremento actualiza `docs/ESTADO_IMPLEMENTACION.md` y `docs/REGISTRO_DEMO.md`.
