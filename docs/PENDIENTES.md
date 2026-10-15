# Pendientes y hoja de ruta

Última actualización: 2026-10-14 (cierre de la sesión 3). Complementa
`docs/ESTADO_IMPLEMENTACION.md` (qué está hecho) y `docs/REGISTRO_DEMO.md` (bitácora).

## 1. Qué se avanzó (resumen)

| Fase | Resultado |
|---|---|
| 0 | Esqueleto hexagonal, reglas de arquitectura verificadas (import-linter + pruebas AST), infraestructura comentada |
| 1 | Capacidad de flota P1–P9 con casos de uso, solver OR-Tools, CLI y 98 % de cobertura del dominio |
| 2 | Multi-tenancy en memoria, Argon2id, JWT + refresh rotatorio, RBAC de 5 roles, auditoría, API HTTP endurecida |
| 3 | Ruteo dinámico: tiempos, plan de la mañana (OR-Tools + heurística), eventos, propuestas, versiones, indicadores |
| 5 | GPS simulado, geocerca, "sin señal", seguimiento programado y SSE |
| 4 | Generador sintético y 4 modelos de ML (scikit-learn) con registro por empresa y verificación de hash |
| 6 | Frontend: las 9 pantallas (incluye maestros y parámetros, y patrones detectados) |

Cifras de calidad: backend 869 pruebas (96 % de cobertura total de `src`), frontend 224 pruebas,
linters limpios; `pip-audit` no se pudo ejecutar en este PC (error SSL). Ver `ESTADO_IMPLEMENTACION.md`.

## 2. Lo que falta, por fase

### Fases 3 y 5 — Ruteo dinámico, GPS y tiempo real: HECHO en la sesión 3
Ya está: tiempos, plan de la mañana, eventos, propuestas con aprobación, versiones, indicadores,
torre de control, línea de tiempo, eventos, GPS simulado (geocerca, sin señal), seguimiento
programado, SSE y hoja del conductor (criterios 11 y 12 aprobados por pruebas).
**Falta (menor):** redistribución entre vehículos distintos de la reserva, caché de tiempos en Redis,
alta de conductores y asignación de vehículos (llegará con maestros).

### Fase 4 — Datos sintéticos y machine learning: HECHO en la sesión 3
Ya está: generador determinista, cuatro modelos detrás de puertos, partición temporal, registro con hash,
aislamiento por empresa, reentrenamiento manual y programado, pantalla de patrones y comparación ML vs.
percentil (ver `docs/ML.md`). **Falta (menor):** conectar el riesgo de retraso con la re-secuenciación del
ruteo, curvas de calibración, persistencia real de modelos y un formato de artefacto sin `pickle`.

### Fase 6 — Resto del frontend
HECHO: maestros y parámetros (CRUD, CSV con previsualización, historial con vigencia), Excel en el
servidor y la pantalla "Patrones detectados". **Falta:** asignación de vehículo a conductor desde la
interfaz, revisión visual y responsive de todas las pantallas.

### Fase 7 — Seguridad, documentación y cierre
- Documentos requeridos por `DOCS.MD` §16 que **aún no existen**: `SEGURIDAD_OWASP.md`,
  `MODELO_AMENAZAS.md` (STRIDE: login, carga CSV, eventos, GPS, aprovisionamiento),
  `PRIVACIDAD.md`, `ARQUITECTURA.md` (con matriz SOLID–evidencia), `MULTITENANT.md`,
  `DEMO_GUION.md`, `GLOSARIO.md`, `ROADMAP.md` (ver §4). `ML.md` ya existe.
- Escaneo de secretos (herramienta no instalada), SBOM, CI local, proxy inverso con TLS de
  desarrollo, pruebas E2E con navegador (Playwright) del guion completo, medición de cobertura
  del frontend, pruebas de accesibilidad automatizadas.
- Reporte final que separe implementado / probado / parcial / pendiente / DEMO-ONLY.

## 3. Deuda transversal conocida

| Tema | Detalle |
|---|---|
| Revisión visual | La interfaz nunca se vio en un navegador durante el desarrollo (tampoco el mapa de la torre de control); revisar diseño, responsive y gráficos |
| `scripts/start-demo.ps1` | Se lanzó en la sesión 3 y respondieron la API y Vite; no se revisó el navegador |
| Base de datos | Comentada a propósito (D-001): PostgreSQL/PostGIS ×3, Redis, Alembic `control_plane`/`tenant`, `ProvisionTenant` con BD real, `SecretsPort` con cifrado de conexiones, pruebas de integración y aislamiento reales |
| Persistencia de la demo | Todo en memoria: reiniciar borra sesiones, empresas creadas, auditoría y cambia las contraseñas (D-018) |
| Límite de tiempo del solver | Solo probado el mapeo de estados con dobles; falta una prueba con timeout real |
| Python | Probado en 3.12.0 (sesión 3) y 3.13 |
| `Makefile` | Sin probar (no hay `make`); `make up`/`make seed` no existen |
| Criterios de aceptación 1–10 | No verificables sin la planilla original `Capacidad_Flota_Transportes_VIGIA.xlsx` ni el HTML "Ruteo dinámico VIGIA" |
| Aislamiento multi-tenant | Lógico en memoria, un solo proceso (D-017); falta la demostración con tres PostgreSQL |
| Auditoría | Cubre login, tablero, empresas, eventos, decisiones y control de simulación; faltan cambios de maestros/parámetros con valor anterior y vigencia |
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
| D-027 | Ventanas que cruzan medianoche (`DOCS.MD` §8) | Para la demo se rechazan con explicación; aceptarlas requiere decisión de negocio |
| — | Clasificación legal de los datos de ubicación GPS | Pendiente de revisión jurídica (`PRIVACIDAD.md`) |
| — | Costo variable y de terceros por tipo/corredor | Supuestos sintéticos; reemplazar con datos de finanzas |

## 6. Riesgos

- Sin la planilla original no se puede demostrar fidelidad con el prototipo.
- La demo vive en un solo proceso y en memoria: no demuestra escalabilidad ni persistencia.
- Sin revisión visual ni E2E, errores de interfaz pueden pasar desapercibidos hasta la primera
  presentación.
- El alcance restante (GPS/SSE, hoja del conductor, maestros/CSV/Excel, ML, cierre de seguridad) es
  grande: seguir por incrementos verticales.
- Los escenarios de indicadores son simulaciones; no deben presentarse como mediciones.

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
3. Abrir la torre de control como despachador, avanzar el reloj, inyectar los cuatro eventos y cortar
   la señal de un vehículo; abrir `Mi hoja de ruta` como conductor.
   Siguiente incremento: maestros y parámetros (CRUD, CSV, historial, Excel). Dependencias ya aprobadas y pendientes de
   instalar: `scikit-learn`, `openpyxl`, `playwright` (D-020).
4. Cada incremento actualiza `docs/ESTADO_IMPLEMENTACION.md` y `docs/REGISTRO_DEMO.md`.
