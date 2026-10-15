# Registro de trabajo de la demo

Bitácora cronológica de todo lo realizado. Se actualiza en cada sesión. Solo se registran hechos
comprobados: lo que se ejecutó, lo que salió y lo que **no** se pudo ejecutar.

Leyenda de estado: **Implementado** · **Probado** · **Parcial** · **Pendiente** · **DEMO-ONLY**.

---

## Sesión 1 — 2026-10-13 · Diagnóstico y fases 0 y 1

### 1. Diagnóstico (sin modificar archivos)

Documentos leídos completos: `CLAUDE.md`, `DOCS.MD`, `docs/ESPECIFICACIONES_BACKEND.md`,
`docs/ESPECIFICACIONES_FRONTEND.md`, `PROMPT_INICIAL.txt`, `README_PAQUETE.txt` y
`Especificacion_Desarrollo_Transportes_VIGIA.docx` (texto extraído del XML del `.docx`).

Hallazgos del workspace:

| Elemento | Resultado |
|---|---|
| Planilla `Capacidad_Flota_Transportes_VIGIA.xlsx` | **No encontrada** |
| HTML "Ruteo dinámico VIGIA" | **No encontrado** |
| Python | 3.13.15 (la especificación pide 3.12) |
| Node / npm | **No instalado** |
| Docker | **No instalado** |
| Git | **No instalado** |
| Make | **No instalado** |

Consecuencias: los criterios de aceptación 1–10 de `DOCS.MD` §10 **no se pueden reproducir**
(planilla ausente); el frontend no se puede construir hasta instalar Node; no se puede ejecutar
PostgreSQL/Docker (coherente con dejar la base de datos comentada).

### 2. Decisiones del usuario

- Aprobó el plan por fases (el mensaje fue "Sí").
- **La base de datos no se desarrolla en la demo: queda comentada** → repositorios en memoria
  (DEMO-ONLY) y `infra/docker-compose.yml` con PostgreSQL comentado. Ver D-001.
- Pidió que todo quede registrado en un `.md` → este archivo.
- Interpretación del "Sí" a las preguntas abiertas del plan (ver `docs/DECISIONES.md`, D-007 y
  D-013): se adoptan los supuestos propuestos y quedan marcados **pendientes de validar**.

### 3. Fase 0 — Esqueleto y reglas de arquitectura

Creado (todo bajo `DEMO/`):

- `APP/Backend/` con `pyproject.toml`, `requirements.lock`, paquete `src/fleetplanner/`
  (`domain/`, `application/`, `adapters/`, `bootstrap/`) y `tests/` (unit, contract,
  integration, architecture; `security/` y `ml/` reservados y vacíos).
- `APP/Frontend/` (carpeta vacía: **pendiente**, requiere Node).
- `infra/docker-compose.yml` (servicios PostgreSQL/Redis **comentados**).
- `.gitignore`, `.env.example` (solo placeholders), `Makefile`.
- Reglas de dependencia en `pyproject.toml` (import-linter): capas hexagonales, dominio sin
  infraestructura, aplicación sin adaptadores, adaptadores de salida independientes entre sí,
  entrada sin salida.
- Pruebas de arquitectura (`tests/architecture/`): import-linter ejecutado desde pytest, chequeo
  propio por AST y una **violación forzada en una copia temporal** que debe ser detectada.

Entorno: venv en `APP/Backend/.venv` (Python 3.13.15). Dependencias instaladas con pip:
`ortools`, `numpy`, `pandas` (runtime) y `pytest`, `pytest-cov`, `ruff`, `mypy`, `import-linter`,
`bandit`, `pip-audit`, `hatchling` (dev). Versiones exactas en `APP/Backend/requirements.lock`.

### 4. Fase 1 — Capacidad de flota P1–P9

Dominio (`domain/capacity/`, solo librería estándar): demanda de diseño (P1), ciclo y capacidad
efectiva (P2), flota por balance (P3), proyección a 5 años (P4), Lean (P5), Monte Carlo (P6),
modelo del mix + KPI (P7/P9), propio vs. tercero (P8), resultado persistible.

Aplicación: casos de uso `RunCapacityAnalysis`, `ProjectFiveYears`, `SimulateMonteCarlo`,
`OptimizeFleetMix`, `BuildCapacityDashboard`; puertos `CapacityInputsReader`,
`CapacityResultWriter/Reader`, `FleetMixSolverPort`, `ClockPort`.

Adaptadores: solver OR-Tools/SCIP, repositorio en memoria (DEMO-ONLY), datos sintéticos
(DEMO-ONLY), relojes real y fijo, CLI de informe. `bootstrap` compone todo.

Ejecución de la demo: `python -m fleetplanner.bootstrap capacity` (desde `APP/Backend`).

### 5. Comandos ejecutados y resultados reales

Todos desde `APP/Backend` con el venv.

| Comando | Resultado |
|---|---|
| `pytest -q --cov` | **137 passed**, 0 failed. Cobertura de **dominio: 98 %** (661 sentencias, 6 sin cubrir, ramas incluidas; denominador: `src/fleetplanner/domain`; sin exclusiones) |
| `ruff check src tests` | All checks passed |
| `ruff format src tests` | 67 archivos sin cambios (ya formateados) |
| `mypy` (strict en `domain` y `application`) | Success: no issues found in 50 source files |
| import-linter | Contracts: **5 kept, 0 broken** |
| `bandit -r src` | No issues identified. 2 hallazgos de severidad baja **suprimidos con justificación** (B311: `random` con semilla para reproducibilidad, no seguridad) — ver ESTADO |
| `pip-audit` | No known vulnerabilities found. `fleetplanner` omitido (paquete local, no está en PyPI) |
| `python -m fleetplanner.bootstrap capacity` | Ejecuta de punta a punta; mix devuelto como `optimal` |
| Instalación limpia: venv nuevo + `pip install -r requirements.lock` + `pip install -e . --no-deps` + `pytest` | **137 passed** en el entorno nuevo (se reintentó en una ruta corta porque la carpeta temporal original excede el límite de ruta de Windows, WinError 206; no fue un fallo del lockfile). Venv temporal eliminado |
| Repetición final tras las últimas ediciones | ruff, `ruff format --check`, mypy, pytest (137 passed, dominio 98 %) y bandit: mismos resultados |

**No ejecutado / no verificado:** pruebas de integración contra PostgreSQL/Redis (no existen aún;
Docker ausente), `docker compose`, `make` (ausente; el Makefile no se probó), `npm audit`,
escaneo de secretos (no hay herramienta instalada), SBOM, CI, pruebas del frontend (no existe).

### 6. Incidentes y correcciones (registrados por transparencia)

1. **PuLP 4.0.0 cambió su API** (núcleo en Rust; `LpVariable(lowBound=...)` ya no existe y no trae
   solver incluido). Se descartó PuLP+HiGHS y se implementó el adaptador con **OR-Tools
   (`pywraplp`/SCIP)**, que además se necesitará para ruteo. Se desinstalaron `pulp` y `highspy`. D-003.
2. **Corrupción de acentos por mi propio comando**: un reemplazo con `Set-Content -Encoding utf8`
   de PowerShell 5.1 re-codificó dos archivos (`pyproject.toml`, `bootstrap/container.py`) y les
   agregó BOM. Se detectó por la advertencia de cambio en disco, se reparó con un script Python
   (deshaciendo la doble codificación y quitando el BOM) y se verificó que `pyproject.toml`
   vuelve a parsear y que los acentos son correctos. Desde entonces solo se edita con las
   herramientas de archivo.
3. **Prueba mal calculada (mía)**: `test_design_uses_percentile_not_the_mean` usaba `[10]*9+[100]`,
   cuyo P90 coincide exactamente con la media (19). Se corrigió el dato de prueba a
   `[10]*8+[100]*2` (media 28, P90 100). No se tocó ninguna fórmula para hacerla pasar.
4. **Decodificación en pruebas de arquitectura**: la salida Unicode de import-linter fallaba en
   cp1252; se fijó `PYTHONIOENCODING=utf-8` y decodificación UTF-8 en el subproceso.
5. **Datos sintéticos poco realistas** en la primera corrida (déficit de ~75 % y propio-vs-tercero
   siempre 0 en largo recorrido porque la tarifa de tercero no cubría ni el costo variable de un
   vehículo propio). Se ajustaron demanda y tarifas **del dataset sintético**, no el algoritmo.
6. Un archivo de pruebas se escribió con un import inexistente por error y se reescribió
   completo antes de ejecutar nada.

### 7. Cierre de las fases 0 y 1

Se pidió aprobación para la fase 2 y para las decisiones abiertas (ver sesión 2).

---

## Sesión 2 — 2026-10-13 · Fase 2 (backend de tenancy/seguridad) + primer frontend

### 1. Decisiones del usuario en esta sesión

1. **D-007 (volumen nuevo en la proyección):** "sí, por ahora lo podemos manejar así" → se mantiene
   el supuesto provisional (suma cada año desde el año de entrada).
2. **OTIF:** "se puede manejar con varios ejemplos (100 %, 90 %, etc.; es un demo)". Se registra
   como D-013 actualizada: en la fase de ruteo se sembrarán **varios escenarios de demostración**
   con distinto nivel de cumplimiento (p. ej. 100 %, 90 %, ...), claramente etiquetados como
   ejemplos sintéticos. No se ha implementado aún (el ruteo es la fase 3).
3. **Aprobó la fase 2** y fijó la prioridad: "lo importante es tener la demo en frontend y en
   backend". Se priorizó entonces tener una pantalla navegable de punta a punta antes de construir
   el resto de módulos. La pregunta sobre instalar Node quedó sin respuesta explícita; se interpretó
   como autorizada por esa prioridad y se instaló **de forma local al usuario** (sin tocar el sistema).

### 2. Backend — fase 2

- **Dominio** (`domain/tenancy/`): `Tenant`, `User`, `Role` (5 roles), `Principal` (identidad
  autenticada, única fuente confiable del tenant), `AccessPolicy`/`Permission` (RBAC con denegación
  por defecto), política de contraseñas (12–128, letra y número) y `LockoutPolicy` (bloqueo
  progresivo desde el 5.º fallo: 30 s, 60 s, 120 s... tope 15 min).
- **Aplicación:** casos de uso `Login`, `RefreshSession`, `Logout`, `AuthenticateRequest`,
  `GetCapacityDashboard`, `ListTenants`, `SetTenantStatus`, `ProvisionTenant` (idempotente por
  slug), `ListAuditEvents`. Puertos: `TenantRegistryPort`, `UserRepositoryPort`,
  `PasswordHasherPort`, `TokenServicePort`, `RefreshTokenStorePort`, `AuditLogPort`,
  `RateLimiterPort`, `TenantWorkspaceProvider`.
- **Adaptadores:** Argon2id (`argon2-cffi`), JWT HS256 (`PyJWT`), refresh tokens opacos con rotación
  y detección de reutilización, auditoría y límite de tasa en memoria (DEMO-ONLY), proveedor de
  espacios de trabajo por tenant.
- **HTTP (FastAPI):** `/api/v1/auth/{login,refresh,logout}`, `/me`, `/capacity/dashboard`,
  `/tenants` (+ suspend/reactivate), `/audit`, `/health`. Errores con código estable y mensaje en
  español; cabeceras de seguridad; CORS en lista blanca; documentación de la API solo en entorno
  `local`; límite de tamaño de cuerpo.
- **Composición:** `bootstrap/application.py` (ensamblado y seed), `bootstrap/settings.py`
  (configuración con fallo seguro). Comando: `python -m fleetplanner.bootstrap serve`.
- **Aislamiento de tenant en memoria:** cada empresa tiene su propio lector de datos, repositorio de
  resultados y casos de uso (`TenantWorkspace`). Ningún caso de uso ni repositorio de datos recibe un
  `tenant_id` libre; el tenant sale de la `Principal` autenticada.

### 3. Frontend — primera versión (React + TypeScript + Vite)

Pantallas: inicio de sesión; tablero de capacidad (KPI, flota por método y tipo con gráfico y tabla,
proyección a 5 años con 3 escenarios, mix, propio vs. tercero, detalle por corredor, hallazgos y
advertencias, exportación CSV con neutralización de fórmulas); administración de empresas (solo
superadministrador, con confirmación y contraseña inicial mostrada una vez); auditoría; página
"Próximamente" para roles cuyas pantallas aún no existen. Etiqueta persistente
**DATOS DE DEMOSTRACIÓN**.

Seguridad de sesión en el navegador: el access token vive solo en memoria; el refresh token es una
cookie `HttpOnly`, `SameSite=Strict`, con ruta `/api/v1/auth`; nada en `localStorage`.

### 4. Node instalado de forma local

Se descargó el zip portable de Node **v24.21.0 (LTS)** desde nodejs.org a una carpeta nueva y se
**verificó el SHA-256** contra `SHASUMS256.txt` (coincidió: `158f7685…e541`) antes de extraerlo en
`%LOCALAPPDATA%\fleetplanner-tools\node`. No se modificó el PATH global ni se necesitó
administrador. `node_modules` está en una unión (junction) hacia
`%LOCALAPPDATA%\fleetplanner-tools\frontend_node_modules` para que **OneDrive no sincronice** miles
de archivos. Reproducible con `scripts/setup-frontend.ps1`.

### 5. Comandos ejecutados y resultados reales (sesión 2)

Backend (desde `APP/Backend`):

| Comando | Resultado |
|---|---|
| `pytest --cov` | **288 passed**, 0 failed. Cobertura de dominio **98 %** (801 sentencias, 10 sin cubrir, con ramas) |
| `ruff check src tests` / `ruff format` | limpio |
| `mypy` (strict en domain/application) | sin errores en 72 archivos |
| import-linter | 5 contratos cumplidos, 0 rotos |
| `bandit -r src` | sin hallazgos activos (2 supresiones justificadas B311 de la sesión 1) |
| `pip-audit` | sin vulnerabilidades conocidas |
| `python -m fleetplanner.bootstrap serve` (proceso real con uvicorn) | arranca; `/health` responde `{"status":"ok"}` |

Frontend (desde `APP/Frontend`, con el Node local):

| Comando | Resultado |
|---|---|
| `tsc --noEmit` | sin errores (strict, `noUncheckedIndexedAccess`) |
| `vitest run` | **79 passed**, 0 failed (3 archivos: formatos/CSV, cliente API, aplicación) |
| `npm audit` | 0 vulnerabilidades |
| `vite build` | correcto; bundle inicial 284 kB, pantalla de capacidad 411 kB (carga diferida) |

Integración real (backend + Vite, recorrido por el proxy en `localhost:5173`): inicio de sesión
200 con rol y empresa correctos; cookie de refresh presente y `HttpOnly`; tablero 200 con
"DATOS DE DEMOSTRACIÓN"; cabeceras `nosniff`/`DENY`/`no-store`; refresh con cookie 200; sin token 401;
la Empresa B devuelve cifras distintas a la A.

### 6. Incidentes y correcciones (sesión 2)

1. **Fallos de prueba propios, no del código:** (a) una prueba asumía que la documentación de la API
   estaba apagada en el entorno de pruebas, que es `local` (donde está habilitada a propósito) → se
   probó el comportamiento correcto en ambos entornos; (b) una prueba de refresh tras suspender
   usaba la cookie del superadmin porque el cliente compartido la había sobrescrito → se usó un
   cliente aparte; (c) varias aserciones del frontend tenían ambigüedad (texto repetido, aviso de
   carga diferida) → se precisaron. En ningún caso se relajó una validación para conseguir verde.
2. **Fragilidad de accesibilidad:** el nombre accesible de «Suspender/Reactivar» dependía de un
   espacio dentro de un `<span>` oculto; se reemplazó por `aria-label` explícito.
3. **Vite no respondía** al arrancar sin `host` fijo; se fijó `127.0.0.1` en `vite.config.ts`.
4. **Ruta temporal demasiado larga** (WinError 206) al crear un entorno de prueba en la carpeta
   temporal de la sesión; se usó una ruta corta (ver sesión 1).

### 6 bis. Cierre del día y publicación en GitHub

- Se creó `docs/PENDIENTES.md`: lo avanzado, lo que falta por fase, deuda transversal, decisiones de
  negocio abiertas, riesgos, hoja de ruta a producto y cómo retomar.
- **Publicación:** el usuario pidió subir todo a la cuenta de GitHub `DANNY5SALAZAR`. Decisiones
  suyas: repositorio **nuevo y privado**; incluir **todo**, también el `.docx` del cliente y
  `PROMPT_INICIAL.txt`; Git instalado por mí y el inicio de sesión de GitHub lo hace el usuario en
  el navegador (no se guardan tokens).
- **Git:** no estaba instalado. Se descargó PortableGit **2.56.0.2** (release v2.56.0.windows.2) y se
  verificó su SHA-256 contra el *digest* publicado por GitHub
  (`075e158e…f61b`, coincidió) antes de extraerlo en `%LOCALAPPDATA%\fleetplanner-tools\git`.
  Sin cambios en el PATH global ni administrador.
- **Revisión previa a publicar:** búsqueda de secretos con patrón (clave/token/contraseña con valor
  literal): el único hallazgo es una contraseña de ejemplo en una prueba del frontend
  (`Clave-Inicial-9x`), sin valor real. No existe `.env`. Esto **no** equivale a un escaneo de
  secretos con herramienta especializada (sigue pendiente).
- **Commit local:** `f2f3c11` (153 archivos). Remoto configurado:
  `https://github.com/DANNY5SALAZAR/fleetplanner-demo.git`.
- **Push: NO completado desde la herramienta.** Intentos: (1) sin credenciales, el entorno desactiva
  los avisos (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`); (2) con el Git Credential Manager
  y la interactividad activada solo para ese comando, el diálogo de autorización de GitHub se
  canceló (`User cancelled dialog`) por no haber sesión interactiva disponible. No se usó ni se
  pidió ningún token. **Pendiente:** que el usuario ejecute el push en su propia terminal (ver
  `docs/PENDIENTES.md`, sección "Cómo retomar").
- **Aviso:** el repositorio local queda dentro de OneDrive; OneDrive sincroniza la carpeta `.git`,
  lo que a veces provoca conflictos. Si aparecen problemas, mover el repositorio fuera de OneDrive.

### 7. Pendiente / límites (ver `docs/ESTADO_IMPLEMENTACION.md`)

- **No se inspeccionó visualmente la interfaz en un navegador** (no hay herramienta de navegador
  disponible en esta sesión). Lo verificado: tipado, 79 pruebas de componentes, build y el
  recorrido HTTP real. El diseño responsive y el aspecto de los gráficos **no están verificados
  visualmente**.
- No hay pruebas E2E con navegador (Playwright) ni medición de cobertura del frontend.
- Pantallas pendientes: torre de control, línea de tiempo, eventos y re-ruteo, hoja de ruta del
  conductor, indicadores, patrones de ML, maestros/CSV (fases 3–6).
- Pendientes de seguridad: `docs/SEGURIDAD_OWASP.md`, `MODELO_AMENAZAS.md`, `PRIVACIDAD.md`, escaneo
  de secretos, SBOM, TLS/proxy, MFA (declarado fuera del alcance de la demo).
- Siguiente fase propuesta: **fase 3 — ruteo** (tiempos Haversine×1,35 + perfil de velocidad, plan de
  la mañana con OR-Tools y heurística de comparación, eventos con aprobación, versiones del plan) y
  sus pantallas (torre de control con mapa, eventos, hoja de ruta del conductor).

---

## Sesión 3 (2026-10-14) — instalación en un PC nuevo y ruteo dinámico

### 1. Puesta en marcha en este PC
- Python 3.12.0 (antes solo se había probado con 3.13: **ahora también 3.12**), Node portátil
  v24.21.0 por `scripts/setup-frontend.ps1` (SHA-256 verificado).
- `pip` fallaba con `CERTIFICATE_VERIFY_FAILED` (Windows sí confía en el certificado; el pip de Python
  no). Sin desactivar la verificación: se instaló `truststore` (wheel con hash verificado) y se usó
  `pip install --use-feature=truststore`. `editables==0.5` se instaló aparte (dependencia de build de
  hatchling que no está en el lockfile) y el paquete con `--no-build-isolation`.
- Resultado inicial: 288 pytest, 79 vitest, linters limpios. La primera corrida de vitest en frío
  falló una prueba por tiempo de arranque; las siguientes tres pasaron.

### 2. Aprobación
Plan aprobado por el usuario (incrementos: ruteo + torre de control → GPS/SSE → hoja del conductor →
maestros → ML → cierre) y dependencias (D-020). Orden elegido: ruteo primero.

### 3. Incremento 1: ruteo dinámico (implementado y probado)
- Dominio `domain/routing/` (solo librería estándar): geografía, ventanas, modelos con validación
  (criterio 11), evaluación de rutas, heurística, seguimiento, plan versionado, eventos/propuestas,
  KPIs.
- Aplicación `application/use_cases/routing/`: plan de la mañana, planificador de re-ruteo,
  `HandleEvent`, `ApproveReroute`, `TrackFleet`, instantánea de la torre de control, indicadores y
  fachada con RBAC, auditoría y límite de tasa.
- Adaptadores: reloj acelerado, tiempos simulados + respaldo, OR-Tools VRP, repositorio en memoria,
  datos sintéticos (CEDI Funza, 36 clientes en Bogotá para la Empresa A, 22 para la B).
- HTTP: `/api/v1/routing/{tower,track,events,proposals/{id}/decision,simulation,day/reset,plans/{v},indicators}`.
- Frontend: Torre de control (mapa Leaflet), Línea de tiempo (SVG con tabla equivalente), Eventos y
  re-ruteo (formulario, propuestas con impacto, aprobación con confirmación, comparación de versiones)
  e Indicadores diarios (barras con leyenda + tabla; paleta validada con el validador de la guía).
- **Defecto real encontrado y corregido:** `ConfirmDialog` devolvía el foco al botón Cancelar en cada
  render, así que escribir en un campo del diálogo perdía el foco (lo detectó la prueba de aprobación).
- **Defecto encontrado y corregido:** el solver quedaba peor que la heurística por la hora de la matriz
  (D-024).

### 4. Comandos ejecutados y resultados (2026-10-14)
- `pytest --cov`: **490 passed**, cobertura del dominio **98 %**.
- `ruff check src tests`: limpio. `mypy`: sin errores (105 archivos). `import-linter`: 5 contratos
  cumplidos. `bandit -r src`: 0 hallazgos activos.
- `pip_audit`: **no se pudo ejecutar** (error SSL de este PC al consultar PyPI).
- Frontend: `tsc --noEmit` limpio, `vitest`: **128 passed**, `vite build` correcto, `npm audit`: 0.
- Recorrido real por la API (Argon2 + OR-Tools + Empresa A): ver `ESTADO_IMPLEMENTACION.md`.

### 5. Pendiente / límites
- **No hubo revisión visual en un navegador** (no hay herramienta de navegador en la sesión).
- Sin E2E (Playwright), sin cobertura del frontend.
- Criterios 1–10 siguen sin verificarse (falta la planilla). Criterios 11 y 12: aprobados por pruebas.
- Siguiente: GPS simulado y SSE; hoja de ruta del conductor.

### 6. Incrementos 2 y 3 (misma sesión): GPS, tiempo real y hoja del conductor
- **Incremento 2:** `GpsPort` + simulador, geocerca (≥ 100 m / > 5 min), alerta de 15 min sin señal
  (conserva el plan), botón para cortar la señal de un vehículo, tarea programada de seguimiento
  por empresa y flujo SSE autenticado (D-028, D-029).
- **Incremento 3:** hoja de ruta del conductor mobile-first: siguiente parada, enlaces de Google Maps
  (≤ 9 puntos intermedios, encadenados), confirmar entrega, reportar novedad y descargar CSV (D-030).
  Las novedades aparecen en la torre de control. El conductor sembrado queda asignado a `V-01`.
- **Falla de seguridad encontrada por las pruebas y corregida:** el SSE devolvía 200 a los roles sin
  permiso (autorizaba ya dentro del flujo). Ahora autoriza antes de abrirlo.
- **Defecto corregido:** el cliente SSE podía reconectar sin pausa en un bucle cerrado (lo detectó una
  prueba por agotamiento de memoria); ahora espera entre reconexiones.
- **Verificado contra un servidor real (uvicorn):** el SSE llega de forma incremental (uno por
  segundo). **No** se verificó a través del proxy de Vite del entorno de desarrollo.
- **Comandos (2026-10-14):** `pytest --cov` **610 passed** (98 % del dominio); `ruff`, `mypy` (113
  archivos), `import-linter` (5 contratos) y `bandit` limpios; `vitest` **170 passed**, `tsc`, `vite
  build` y `npm audit` limpios. `pip-audit` sigue sin poder ejecutarse (SSL).

### 7. Incremento 4 (misma sesión): maestros, parámetros, CSV, historial y Excel
- **Backend:** módulo `domain/masters` (esquema, catálogo, constructores), servicio de maestros con
  integridad referencial, carga CSV con previsualización (todo o nada), parámetros versionados con vigencia,
  historial solo-agregar, exportador openpyxl y rutas HTTP para administrador de empresa (D-031…D-034).
  El tablero de capacidad y el ruteo leen ahora los maestros editables.
- **Frontend:** pantalla "Maestros y parámetros" (pestañas por área, formularios por esquema, diálogo CSV,
  parámetros con cambio programado, historial filtrable) y botones "Exportar Excel" en capacidad y hoja
  del conductor.
- **Defectos encontrados y corregidos durante el desarrollo:** mensajes de `ValueError` en inglés que
  llegaban al usuario (ahora se traducen), el diálogo de confirmación devolvía el foco a "Cancelar" en cada
  render y se perdía lo escrito, y la lista de métodos permitidos de CORS no incluía PUT/DELETE.
- **Comandos (2026-10-14):** backend `pytest --cov=fleetplanner` **764 passed** (96 % total de `src`);
  `ruff check` y `ruff format --check` limpios; `mypy` sin errores (132 archivos); `lint-imports` 5 contratos
  cumplidos; `bandit -r src` sin hallazgos activos. Frontend: `tsc --noEmit` limpio, `vitest` **207 passed**,
  `vite build` correcto, `npm audit --audit-level=high` 0 vulnerabilidades. `pip-audit` sigue sin poder
  ejecutarse (SSL).
- **Límites:** sin revisión visual en navegador; sin E2E; el vínculo conductor ↔ vehículo no se edita en la
  interfaz.

### 8. Incremento 5 (misma sesión): datos sintéticos y machine learning
- **Dependencia instalada (aprobada):** `scikit-learn 1.9.1` (+ `scipy`, `joblib`, `threadpoolctl`,
  `narwhals`, `cloudpickle`), con `pip --use-feature=truststore`; fijadas en `requirements.lock`.
- **Backend:** `domain/ml` (calendario de festivos de Colombia, métricas, partición temporal, tipos),
  `application/use_cases/ml` (`MlService`, accesos, reentrenamiento programado), adaptadores scikit-learn
  y registro con hash, generador sintético, endpoints `GET /api/v1/patterns` y `POST /api/v1/patterns/retrain`,
  y pronóstico ML en el tablero de capacidad (D-035…D-037).
- **Frontend:** pantalla "Patrones detectados" (pronóstico con intervalo y tabla, anomalías, riesgo de
  retraso, segmentos, procedencia de modelos, límites) y panel "ML frente al percentil" en capacidad.
- **Documentación nueva:** `docs/ML.md` (modelos, datos, métricas honestas, aislamiento, límites).
- **Hallazgos de las pruebas / mediciones:** el P90 cubrió 79,6 % en la prueba (por debajo del 90 %
  nominal) y el recall del riesgo de retraso fue 25,7 %; se declararon como límites, no se ajustaron los
  umbrales para "pasar".
- **Comandos (2026-10-14):** backend `pytest --cov=fleetplanner` **845 passed** (96 % total de `src`);
  `ruff check`/`ruff format --check` limpios; `mypy` sin errores (153 archivos); `lint-imports` 5
  contratos cumplidos; `bandit -r src`: 0 hallazgos, 6 supresiones justificadas. Frontend: `tsc --noEmit`
  limpio, `vitest` **224 passed**, `vite build` correcto, `npm audit --audit-level=high` 0 vulnerabilidades.
  `pip-audit` sigue sin poder ejecutarse (SSL).
- **Límites:** sin revisión visual en navegador, sin E2E, métricas solo sobre datos sintéticos.

### 9. Demo compartida (misma sesión): contraseñas por entorno e interfaz servida por la API
- **Cambios:** `bootstrap/settings.py` (HOST, PORT, FRONTEND_DIST, DEMO_PASSWORD, DEMO_SUPERADMIN_PASSWORD),
  `seed_demo` con contraseñas opcionales, `serve --host/--port`, interfaz compilada servida por la API con CSP
  propia, `Dockerfile`, `.dockerignore`, `requirements-runtime.lock`, `scripts/share-demo.ps1` y
  `docs/HOSPEDAJE_DEMO.md` (D-038).
- **Verificado:** pruebas nuevas en `tests/security/test_shared_hosting.py` (configuración, contraseñas,
  servicio de la interfaz, recorrido de rutas, CSP, mismo origen). Arranque real en local con
  `FLEETPLANNER_ENV=production`: `/` y `/capacidad` devuelven la interfaz, los activos con caché larga, el
  inicio de sesión funciona para gerencia, conductor, despachador (Empresa B) y superadmin, una contraseña
  incorrecta da 401, `/api/v1/docs` da 404, y las contraseñas y la clave **no** aparecen en la salida del
  servidor.
- **No verificado:** construcción de la imagen Docker, ejecución en Railway, túnel real, SSE a través de un
  proxy, y la interfaz en un celular.

