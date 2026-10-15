# Estado de implementación

Última actualización: 2026-10-14 (sesión 3: ruteo dinámico, torre de control, eventos,
indicadores, GPS simulado, tiempo real, hoja de ruta del conductor, maestros y parámetros, ML y patrones). Evidencia de cada comando: `docs/REGISTRO_DEMO.md`.

## Resumen por fase

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Esqueleto, reglas de arquitectura, infra comentada, documentación base | **Implementada y probada** |
| 1 | Capacidad de flota P1–P9 (dominio, casos de uso, solver, CLI) | **Implementada y probada** con datos sintéticos y casos a mano |
| 2 | Multi-tenancy en memoria, JWT/Argon2id, RBAC, auditoría, API HTTP | **Implementada y probada** (en memoria, DEMO-ONLY) |
| 3 | Ruteo: tiempos, plan de la mañana, eventos, propuestas, versionado, indicadores | **Implementada y probada** salvo lo listado en "Fase 3: lo que falta" |
| 4 | Generador sintético y 4 modelos de ML (scikit-learn detrás de puertos) | **Implementada y probada** con datos sintéticos (DEMO-ONLY); métricas y límites en `docs/ML.md` |
| 5 | Simulador GPS (`GpsPort`), geocerca, "sin señal", SSE, tarea programada | **Implementada y probada** (GPS simulado, DEMO-ONLY): lecturas cada 2 min simulados, geocerca de 100 m > 5 min, alerta a los 15 min sin señal, tarea programada y SSE autenticado por empresa |
| 6 | Frontend completo (9 pantallas) | **Implementada y probada en componentes**; **sin revisión visual en navegador**, sin E2E |
| 7 | Informe OWASP, modelo de amenazas, privacidad, guion, E2E, reporte final | Pendiente |

## Pantallas del frontend

| Pantalla (`DOCS.MD` §9) | Rol | Estado |
|---|---|---|
| Inicio de sesión / sesión / cierre | todos | Implementada y probada (pruebas de componentes) |
| 1. Torre de control con mapa (Leaflet + OpenStreetMap) | despachador | Implementada y probada (componentes + recorrido real por la API). **Sin revisión visual en navegador** |
| 2. Línea de tiempo por vehículo | despachador | Implementada y probada (componentes) |
| 3. Eventos, propuesta, aprobación/rechazo, comparación de versiones | despachador | Implementada y probada (componentes + API) |
| 4. Hoja de ruta del conductor (celular, Google Maps, confirmar entrega, novedad, CSV) | conductor | Implementada y probada (componentes + API). **Sin revisión visual en un celular real** |
| 5. Tablero de capacidad | gerencia, admin | Implementada y probada; pronóstico ML frente al percentil (datos sintéticos); exportación CSV y Excel `.xlsx` generado en el servidor |
| 6. Maestros y parámetros (CRUD, carga CSV con previsualización, parámetros versionados, historial, Excel) | admin de empresa | Implementada y probada (componentes + API). **Sin revisión visual en navegador** |
| 7. Indicadores diarios (puntualidad, OTIF, estático vs. dinámico) | gerencia, despachador | Implementada y probada. Escenarios **simulados** con datos sintéticos |
| 8. Patrones detectados (pronóstico, anomalías, riesgo de retraso, segmentos, procedencia de modelos) | gerencia, despachador (reentrenar: gerencia) | Implementada y probada (componentes + API). Datos **sintéticos**. **Sin revisión visual en navegador** |
| 9. Administración de empresas | superadmin | Implementada y probada; migración por tenant: pendiente |
| Auditoría (no numerada) | admin, superadmin | Implementada y probada |

Ya no quedan pantallas pendientes en la navegación; las limitaciones están en cada fila.

## Backend

| Capacidad | Implementado | Probado | Notas |
|---|---|---|---|
| P1–P9 de capacidad | Sí | Sí | ver fase 1 abajo |
| RBAC con denegación por defecto (5 roles) | Sí | Sí (matriz por rol, HTTP y dominio) | incluye los endpoints de ruteo e indicadores |
| Login, JWT + refresh rotatorio, aislamiento entre empresas, suspensión | Sí | Sí (a nivel de aplicación en memoria) | D-016, D-017 |
| Tiempos de viaje: Haversine × 1,35 + perfil de velocidad + cierres | Sí (DEMO-ONLY) | Sí | `TrafficTimePort` + respaldo; D-026 |
| Falla del proveedor de tiempos → perfil de velocidad + "Tiempos estimados sin tráfico" | Sí | Sí (dominio de aplicación y HTTP) | **Criterio 12** |
| Validación de clientes/ventanas (lat. 40 y ventana 14:00–10:00 se rechazan con explicación) | Sí | Sí (dominio y HTTP) | **Criterio 11**; ventanas que cruzan la medianoche no se aceptan (D-027) |
| Plan de la mañana: OR-Tools (VRP con ventanas y capacidad) + heurística de comparación | Sí | Sí (contrato por motor, determinismo, capacidad, ventanas) | D-024; se descarta todo plan que viole capacidad |
| Eventos: cierre vial, pedido urgente, cambio de ventana, avería | Sí | Sí (flujo completo y HTTP) | D-021, D-022, D-023 |
| Propuestas que solo se aplican con aprobación; versiones inmutables con motivo, usuario, fecha y decisión | Sí | Sí | la versión anterior no se toca (probado) |
| Regla "una carga no cambia de vehículo salvo transbordo/recarga" | Sí | Sí | transbordo de 25 min; recarga de 20 min |
| Seguimiento (`TrackFleet`): retraso proyectado → propuesta de re-secuenciar | Sí | Sí | una propuesta a la vez; no reinsiste tras un rechazo |
| Reloj acelerado (pausa, velocidad, avance, reinicio) por empresa | Sí (DEMO-ONLY) | Sí | `SimulationClockPort`; se pausa al haber propuesta pendiente |
| Indicadores: puntualidad ≠ OTIF, mismo denominador; escenarios estático vs. dinámico | Sí | Sí | D-025; **simulaciones**, no mediciones |
| Auditoría de eventos, decisiones, control de simulación y reinicio; límite de tasa (30 eventos/min, 6 reinicios/min por usuario) | Sí | Sí | |
| GPS simulado detrás de `GpsPort`: lecturas cada 2 min simulados, posición según el plan, corte de señal por vehículo | Sí (DEMO-ONLY) | Sí | D-028 |
| Geocerca de 100 m mantenida > 5 min → entrega confirmada ("geocerca"); la primera confirmación gana | Sí | Sí (dominio y flujo) | D-028 |
| Alerta "sin señal" a los > 15 min con la antigüedad de la última posición; se conserva el plan | Sí | Sí | **no re-planifica** (probado) |
| Tarea programada de seguimiento (cada 2,5 s, por empresa, omite días en pausa y empresas suspendidas, tolera fallos) | Sí | Sí | D-029; el tenant sale del registro central |
| Flujo en tiempo real (SSE): identidad y empresa revalidadas en cada evento, cierre cada 55 s, 4 conexiones por usuario | Sí | Sí (HTTP y servidor real con uvicorn) | D-029; **no se verificó a través del proxy de Vite** |
| Hoja del conductor: su ruta, enlaces de Google Maps (≤ 9 puntos intermedios, encadenados), confirmar entrega, novedades | Sí | Sí (dominio, flujo y HTTP) | D-030; el vehículo sale del usuario guardado |
| Maestros (tipos de vehículo, corredores, clientes, vehículos…) con CRUD guiado por esquema; la validez la define el constructor del dominio | Sí | Sí (dominio, servicio y HTTP) | D-031; no se borra lo que otro registro referencia (409) |
| Carga CSV: ≤ 200 KB y ≤ 5000 filas, `,` o `;`, todo o nada, previsualización con fila/columna, texto con forma de fórmula rechazado | Sí | Sí | D-032 |
| Parámetros versionados con vigencia futura y motivo; el pasado no se reescribe; historial de cambios solo-agregar con antes/después | Sí | Sí | D-033 |
| El tablero de capacidad y el ruteo leen los maestros editables (con la siembra reproducen los resultados originales) | Sí | Sí | D-031 |
| Exportación `.xlsx`/CSV en el servidor (capacidad, maestros, hoja del conductor): neutralización de fórmulas, nombres de archivo seguros, auditada | Sí | Sí | D-034 |
| Generador sintético reproducible (90 días por empresa, patrones sembrados) detrás de `HistoryReaderPort` | Sí (DEMO-ONLY) | Sí (determinismo, empresas distintas, patrones presentes) | D-035 |
| 4 modelos de ML: demanda P50/P90, anomalías, riesgo de retraso, segmentos; partición temporal; baseline; importancia por permutación | Sí | Sí (comportamiento en el fixture; el modelo supera la línea base, el detector halla lo sembrado) | D-035; **P90 cubre 79,6 % (< 90 % nominal)**, recall del retraso 25,7 % |
| Registro de modelos por empresa: versión, fecha, métricas, SHA-256, verificación antes de cargar | Sí | Sí (artefacto alterado → no se carga) | D-036; en memoria |
| Aislamiento de ML por empresa (lector, registro y modelos propios) | Sí | Sí (servicio y HTTP) | D-035 |
| Reentrenamiento manual (gerencia, 3/min, auditado) y programado (24 h, solo empresas ya entrenadas) | Sí | Sí | D-037 |
| Pronóstico ML frente al percentil en el tablero de capacidad (degrada con advertencia si falla) | Sí | Sí | D-037 |
| Riesgo de retraso alimentando la re-secuenciación del ruteo | No | — | Pendiente: hoy es informativo |
| Modo compartido: interfaz servida por la API, contraseñas fijas por entorno, CSP de la interfaz | Sí | Sí (pruebas + arranque real local) | D-038; Docker/Railway/túnel **no verificados** |
| Cifrado de secretos de conexión (`SecretsPort`) | No | — | No hay conexiones: BD comentada |
| Persistencia PostgreSQL / Redis | No (comentado) | — | D-001 |

### Fase 3: lo que falta
- Redistribución de pedidos entre vehículos distintos de la reserva (hoy solo se re-secuencia por
  vehículo, se recarga o se transborda).
- Caché de la matriz de tiempos en Redis (TTL 15 min): no hay Redis.
- Un conductor por empresa en la siembra (`conductor` → `V-01`); el vehículo del conductor es un atributo
  de usuario que **todavía no se edita desde la interfaz** (los maestros administran vehículos, no usuarios).

## Calidad (última ejecución, 2026-10-14)

Backend:

| Control | Resultado |
|---|---|
| pytest | **869 passed**, 0 failed |
| Cobertura (`pytest --cov=fleetplanner`, todo `src`, con ramas) | **96 %** total (8174 sentencias, 205 sin cubrir). El desglose del dominio no se volvió a medir; la última medición (antes del incremento 4) fue 98 % |
| Ruff | limpio |
| mypy strict (domain/application) | sin errores (153 archivos) |
| import-linter | 5 contratos cumplidos, 0 rotos |
| Bandit | 0 hallazgos activos; **6 supresiones justificadas** (B311 PRNG con semilla ×4; B403/B301 `pickle` de artefactos propios con hash verificado, D-036) |
| pip-audit | **No se pudo ejecutar** en este PC (error de certificados SSL al consultar PyPI). Pendiente |

Frontend:

| Control | Resultado |
|---|---|
| `tsc --noEmit` (strict) | sin errores |
| vitest | **224 passed**, 0 failed (37 de maestros/Excel, 17 de patrones) |
| `npm audit` | 0 vulnerabilidades |
| `vite build` | correcto |
| Cobertura del frontend | **no medida** |

Servidor real (uvicorn) + cliente HTTP real: el SSE entrega un estado por segundo (reloj a 120×:
+2 min simulados por evento) con `Cache-Control: no-store`.

Recorrido real (Argon2 + OR-Tools + datos de la Empresa A, por la API en proceso): día creado en
3,4 s; cierre → propuesta → aprobación; avería → reserva; escenarios de indicadores en 7 s la
primera vez y 0,01 s en caché; la Empresa B no ve eventos de la A; el conductor recibe 403.

## Fase 1 por algoritmo

| Id | Algoritmo | Implementado | Probado | Notas |
|---|---|---|---|---|
| P1 | Demanda de diseño | Sí | Sí (a mano) | D-005 |
| P2 | Ciclo y capacidad efectiva | Sí | Sí (a mano) | |
| P3 | Flota por balance | Sí | Sí (a mano) | D-006 |
| P4 | Proyección 5 años, 3 escenarios | Sí | Sí | D-007 aceptada para la demo |
| P5 | Lean | Sí | Sí (a mano) | D-009 |
| P6 | Monte Carlo | Sí | Sí (reproducibilidad, positividad) | D-008 |
| P7 | Mix MIP | Sí (OR-Tools/SCIP) | Contrato: óptimo, restricciones, infactible. **Límite de tiempo: solo el mapeo de estados con dobles** | D-003 |
| P8 | Propio vs. tercero | Sí | Sí (a mano) | D-010 |
| P9 | Tablero/KPI | Sí (API + pantalla) | Sí | OTIF de capacidad sigue "No disponible"; el OTIF vive en Indicadores diarios |

## Criterios de aceptación de `DOCS.MD` §10

- **1–10: NO verificados contra la planilla de referencia** (no está disponible). Las cifras de la
  demo (p. ej. 48 vehículos, 36 clientes) son de un dataset sintético y **no reproducen** esas
  referencias. Esto incluye 7–10 (ruteo sin eventos, cierre de la Calle 80, OTIF 84 % / 100 %): el
  guion de eventos de la demo es parecido pero **no equivalente** y sus cifras son otras.
- **11:** cubierto por pruebas (`test_geo_models_evaluation.py::TestCriterion11CustomerValidation`
  y `test_routing_http.py::TestEventValidation`). Aprobado para el comportamiento de validación.
- **12:** cubierto por pruebas (`test_routing_flow.py::TestTravelProviderFailure` y
  `test_routing_http.py::TestFlowOverHttp::test_provider_failure_toggle_shows_the_notice`).
  Aprobado para el comportamiento descrito.

## No ejecutado / no verificado
- **Revisión visual de la interfaz en un navegador y en un celular** (diseño responsive, mapa,
  hoja del conductor, aspecto de los gráficos): no hay herramienta de navegador en la sesión. Solo pruebas de componentes (el mapa de
  Leaflet se ejecuta en jsdom, sin teselas), tipado, build y recorrido HTTP real.
- Pruebas E2E con navegador (Playwright), cobertura del frontend, accesibilidad automatizada.
- Pruebas contra PostgreSQL/Redis, `docker compose`, `make`, escaneo de secretos, SBOM, CI,
  `pip-audit` (error SSL local).
- Pruebas de rendimiento y de carga.
- Límite de tiempo real del solver de capacidad (solo mapeo de estados con dobles).

## Limitaciones conocidas
- Aislamiento lógico en memoria en un solo proceso (D-017). Reiniciar el backend borra sesiones,
  auditoría, empresas dadas de alta, el día operativo y regenera las contraseñas (D-018).
- Los trayectos se dibujan en línea recta y las posiciones se interpolan entre paradas (DEMO-ONLY).
- OR-Tools usa una matriz de tiempos única (media jornada); el puntaje final lo calcula siempre el
  evaluador de dominio con la velocidad de cada hora (D-024).
- Monte Carlo asume independencia entre corredores (D-008).
- Los escenarios de indicadores tardan unos 7 s la primera vez por empresa y luego quedan en caché
  del proceso.

## Siguiente paso recomendado
Fase 7: documentos pendientes de `DOCS.MD` §16 (`SEGURIDAD_OWASP.md`, `MODELO_AMENAZAS.md`,
`PRIVACIDAD.md`, `ARQUITECTURA.md`, `MULTITENANT.md`, `DEMO_GUION.md`, `GLOSARIO.md`, `ROADMAP.md`), pruebas E2E
con Playwright, escaneo de secretos/SBOM y el informe final que separe implementado / probado / parcial /
pendiente / DEMO-ONLY.
