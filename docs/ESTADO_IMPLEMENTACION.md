# Estado de implementación

Última actualización: 2026-10-13 (fin de la sesión 2: fase 2 de backend y primer frontend).
Evidencia de cada comando: `docs/REGISTRO_DEMO.md`.

## Resumen por fase

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Esqueleto, reglas de arquitectura, infra comentada, documentación base | **Implementada y probada** |
| 1 | Capacidad de flota P1–P9 (dominio, casos de uso, solver, CLI) | **Implementada y probada** con datos sintéticos y casos a mano |
| 2 | Multi-tenancy en memoria, JWT/Argon2id, RBAC, auditoría, API HTTP | **Implementada y probada** (en memoria, DEMO-ONLY) |
| 3 | Ruteo: tiempos, plan de mañana, eventos, versionado | Pendiente (incluye escenarios de OTIF de ejemplo, D-013) |
| 4 | Generador sintético y 4 modelos de ML | Pendiente |
| 5 | Simulador GPS, reloj acelerado, SSE | Pendiente |
| 6 | Frontend completo (9 pantallas) | **Parcial**: login, capacidad, empresas, auditoría hechas; faltan torre de control, línea de tiempo, eventos, hoja de ruta, indicadores, patrones ML, maestros/CSV |
| 7 | Informe OWASP, modelo de amenazas, privacidad, guion, E2E, reporte final | Pendiente |

## Pantallas del frontend

| Pantalla (`DOCS.MD` §9) | Estado |
|---|---|
| Inicio de sesión / sesión / cierre | Implementada y probada (pruebas de componentes) |
| 5. Tablero de capacidad (KPI, flota por método/tipo, 5 años y 3 escenarios, mix, propio vs. tercero, corredores, hallazgos, exportación CSV) | Implementada y probada; **ML vs. percentil: no disponible** (declarado en pantalla) |
| 9. Administración de tenants (solo superadministrador) | Implementada y probada; migración por tenant: pendiente |
| Auditoría (no numerada en la especificación) | Implementada y probada |
| 1–4 (torre de control, línea de tiempo, eventos, hoja de ruta) | Pendiente (fase 3 y 5) |
| 6. Maestros y parámetros (CRUD, CSV, historial) | Pendiente |
| 7. Indicadores diarios | Pendiente |
| 8. Patrones de ML | Pendiente |

Las pantallas pendientes aparecen en la navegación **deshabilitadas y explicadas** ("Próximamente").

## Backend

| Capacidad | Implementado | Probado | Notas |
|---|---|---|---|
| P1–P9 de capacidad | Sí | Sí | ver fase 1 abajo |
| RBAC con denegación por defecto (5 roles) | Sí | Sí (matriz por rol, HTTP y dominio) | |
| Login: Argon2id, mensaje genérico, igualación de tiempos, bloqueo progresivo, límite de tasa | Sí | Sí | MFA: fuera del alcance de la demo |
| JWT 15 min + refresh rotatorio con detección de reutilización + revocación al cerrar sesión | Sí | Sí | D-016 |
| Aislamiento entre empresas (token, ID manipulado, cabeceras, query, concurrencia, suspensión) | Sí | Sí (a nivel de aplicación en memoria) | No prueba aislamiento de infraestructura (D-017) |
| Alta idempotente de empresa, suspensión/reactivación con revocación de sesiones | Sí | Sí | Migraciones por tenant: pendientes (sin BD) |
| Auditoría (login, tablero, empresas) y consulta por rol | Sí | Sí | Cambios de maestros/parámetros: pendiente |
| Cabeceras de seguridad, CORS en lista blanca, docs solo en `local`, errores sin trazas, límite de cuerpo | Sí | Sí | CSP/HSTS de la capa estática (proxy TLS): pendiente |
| Configuración con fallo seguro | Sí | Sí | |
| Cifrado de secretos de conexión (`SecretsPort`) | No | — | No hay conexiones: BD comentada |
| Persistencia PostgreSQL / Redis | No (comentado) | — | D-001 |

## Calidad (última ejecución, 2026-10-13)

Backend:

| Control | Resultado |
|---|---|
| pytest | **288 passed**, 0 failed |
| Cobertura del dominio | **98 %** (801 sentencias, 10 sin cubrir; con ramas) — objetivo ≥ 90 % cumplido |
| Ruff | limpio |
| mypy strict (domain/application) | sin errores (72 archivos) |
| import-linter | 5 contratos cumplidos, 0 rotos; violación forzada detectada en prueba |
| Bandit | 0 hallazgos activos; **2 supresiones justificadas** de severidad baja (B311, PRNG con semilla) |
| pip-audit | sin vulnerabilidades conocidas (paquete local omitido) |

Frontend:

| Control | Resultado |
|---|---|
| `tsc --noEmit` (strict) | sin errores |
| vitest | **79 passed**, 0 failed |
| `npm audit` | 0 vulnerabilidades |
| `vite build` | correcto |
| Cobertura del frontend | **no medida** |

Integración real (backend + Vite): recorrido HTTP verificado (login → cookie → tablero → refresh →
401 sin token; empresas A y B con cifras distintas).

## Fase 1 por algoritmo

| Id | Algoritmo | Implementado | Probado | Notas |
|---|---|---|---|---|
| P1 | Demanda de diseño | Sí | Sí (a mano) | D-005 |
| P2 | Ciclo y capacidad efectiva | Sí | Sí (a mano) | |
| P3 | Flota por balance | Sí | Sí (a mano) | D-006 |
| P4 | Proyección 5 años, 3 escenarios | Sí | Sí | D-007 aceptada para la demo |
| P5 | Lean | Sí | Sí (a mano) | D-009 |
| P6 | Monte Carlo | Sí | Sí (reproducibilidad, positividad) | D-008 |
| P7 | Mix MIP | Sí (OR-Tools/SCIP) | Contrato: óptimo, restricciones, infactible. **Límite de tiempo: solo el mapeo de estados con dobles; no se provocó un timeout real** | D-003 |
| P8 | Propio vs. tercero | Sí | Sí (a mano) | D-010 |
| P9 | Tablero/KPI | Sí (API + pantalla) | Sí | OTIF y ML: no disponibles (declarado) |

## Criterios de aceptación de `DOCS.MD` §10

- **1–10: NO verificados contra la planilla de referencia** (no está disponible). Las cifras de la
  demo (p. ej. 48 vehículos) son de un dataset sintético y **no reproducen** esas referencias.
- **11 y 12:** corresponden a validación de clientes/ventanas y al fallo del proveedor de tiempos;
  **pendientes** (fases 3 y 5). No se declaran aprobados.

## No ejecutado / no verificado
- **Revisión visual de la interfaz en un navegador** (diseño responsive, aspecto de los gráficos):
  no hubo herramienta de navegador; solo pruebas de componentes, tipado, build y recorrido HTTP.
- Pruebas E2E con navegador (Playwright), cobertura del frontend, accesibilidad automatizada.
- Pruebas contra PostgreSQL/Redis, `docker compose`, `make`, escaneo de secretos, SBOM, CI.
- Pruebas de rendimiento y de carga; `scripts/start-demo.ps1` (validada su sintaxis, **no lanzado**).
- Python 3.12 (solo 3.13).

## Limitaciones conocidas
- Aislamiento lógico en memoria en un solo proceso (D-017). Reiniciar el backend borra sesiones,
  auditoría, empresas dadas de alta y resultados (todo en memoria) y regenera las contraseñas (D-018).
- Monte Carlo asume independencia entre corredores (D-008).
- El análisis propio-vs-tercero descarta días con algún dato ausente (`days_used` informa cuántos).
- El tablero se recalcula completo en cada petición (rápido con los datos de la demo; no hay caché).

## Siguiente paso recomendado
Fase 3 (ruteo) con sus pantallas de torre de control, eventos/re-ruteo y hoja de ruta del conductor,
incluidos los escenarios de OTIF de ejemplo (D-013). Requiere Leaflet (mapa) como dependencia nueva
del frontend.
