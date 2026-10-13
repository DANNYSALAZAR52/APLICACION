# Decisiones (ADR corto)

Formato: contexto · decisión · consecuencias. Estado: **Adoptada** o **Pendiente de validar**
con negocio.

## D-001 — Persistencia en memoria; PostgreSQL comentado
- **Contexto:** el usuario indicó que, al ser una demo, la base de datos no se desarrolla por
  ahora y debe quedar comentada. Además Docker no está instalado.
- **Decisión:** los puertos de repositorio se implementan con adaptadores en memoria
  (DEMO-ONLY). Los adaptadores SQLAlchemy/PostgreSQL y `docker-compose` quedan descritos y
  comentados (`adapters/outbound/persistence_sql/`, `infra/docker-compose.yml`).
- **Consecuencias:** la arquitectura hexagonal permite sustituirlos sin tocar dominio ni casos
  de uso. No hay pruebas de integración contra PostgreSQL; el aislamiento multi-tenant se
  demostrará con almacenes en memoria separados por tenant, no con tres instancias reales.

## D-002 — Nombre del paquete: `fleetplanner`
- **Decisión:** nombre genérico, sin referencia a un cliente. Los tenants se llaman Empresa Demo
  A/B. **Consecuencia:** el nombre "VIGIA" del `.docx` no aparece en código ni rutas.

## D-003 — OR-Tools (SCIP) en lugar de PuLP para el mix
- **Contexto:** PuLP 4.0.0 cambió de API y no incluye solver; las instrucciones y firmas
  conocidas no coinciden.
- **Decisión:** `pywraplp` con SCIP detrás de `FleetMixSolverPort`. `DOCS.MD` admite OR-Tools o
  PuLP. **Consecuencia:** una dependencia menos que mantener; OR-Tools también servirá al ruteo.

## D-004 — El dominio usa solo librería estándar
- **Decisión:** estadísticos (`mean`, desviación, percentiles), Monte Carlo (`random.Random` con
  semilla) y redondeo están implementados en dominio sin NumPy/Pandas. Verificado por import-linter
  y por prueba AST. **Consecuencia:** más código propio, pero dominio puro y fácil de probar.

## D-005 — Ventana de demanda de diseño (P1)
- **Decisión:** los últimos 60 días **calendario** terminando en la última fecha con observación
  del corredor; un día sin dato queda fuera (no es cero); mínimo 2 días válidos (para la
  desviación). Un corredor con menos días se excluye con advertencia, no se rellena.
- **Percentil:** interpolación lineal (equivale a `PERCENTIL.INC`).

## D-006 — Redondeo de flota (P3)
- **Decisión:** se suman las fracciones por tipo, se multiplica por (1 + reserva) y se redondea
  hacia arriba **una vez**, con tolerancia de 1e-9 para no inflar por ruido de punto flotante.
  Cubierto por pruebas (ejemplo 3,75 → ×1,08 = 4,05 → 5; redondear antes por corredor daría 6).

## D-007 — Volumen nuevo en la proyección (P4) · **Aceptada para la demo; validar antes de producción**
- **Actualización 2026-10-13:** el usuario aceptó manejarlo así "por ahora". Sigue sin validarse con
  negocio: no usar con datos productivos.
- **Contexto:** `DOCS.MD` deja abierto si es adición recurrente o incremento único.
- **Decisión provisional:** toneladas/día adicionales por corredor que se **suman en cada año
  desde el año de entrada (inclusive)**, sin crecer con el CAGR (así lo describe el `.docx`).
  El año 1 de la proyección es `año base + 1`.
- **Consecuencia:** no usar para datos productivos hasta validarlo. Se cambia en
  `domain/capacity/projection.py::project_demand`.

## D-008 — Monte Carlo (P6)
- **Decisión:** demanda y factor de ciclo con distribución **lognormal** (nunca negativos),
  sorteados de forma **independiente por corredor y por día**; factor de ciclo con media 1 y CV
  10 %; flota redondeada hacia arriba por tipo cada día; percentiles por rango más cercano (valor
  observado). La semilla se guarda con cada resultado.
- **Limitación:** la independencia entre corredores subestima la varianza si en la realidad la
  demanda/ciclo están correlacionados (p. ej. un día de lluvia afecta todo).

## D-009 — Definiciones Lean (P5)
- `viajes = demanda_promedio·(1+colchón)/(capacidad·llenado)`.
- % valor agregado = (ida + fracción de retorno con backhaul)/ciclo.
- % muda = (espera en muelle + espera en cliente + retorno vacío)/ciclo.
- Takt = minutos operativos / viajes requeridos.

## D-010 — Propio vs. tercero (P8)
- **Decisión:** se optimiza **por tipo de vehículo** (los costos son separables por tipo). El
  historial `R` usa solo los días en que **todos** los corredores tienen dato; no se aplica
  reserva a `R`. El rango de búsqueda es `0..max(R)` (derivado del historial; más allá solo suma
  costo fijo). Empate → menor N. El costo variable por vehículo-día es el promedio ponderado por
  flota fraccional de los corredores del tipo.
- **Consecuencia:** es un modelo por tipo; no modela sustitución entre tipos (eso lo hace P7).

## D-011 — Costos del mix (P7) y KPI (P9)
- Costo fijo diario = costo mensual / días por mes configurados. Costo variable = costo/km × km por
  vehículo-día, con km = viajes/día × OEE × 2 × km de ida. El MIP asigna vehículos dedicados por
  corredor (`x[r,t]`) y flota total por tipo (`y[t]`).
- KPI definidos en `domain/capacity/kpis.py`. **OTIF no se calcula** en capacidad (declarado
  `None`): depende del módulo de ruteo.

## D-012 — Sin servicios de pago ni Google APIs
- **Contexto:** el `.docx` propone Google Routes/Geocoding; `DOCS.MD` y `CLAUDE.md` lo prohíben
  en la demo básica. **Decisión:** se sigue `DOCS.MD` (Haversine×1,35 + perfil de velocidad,
  Leaflet/OSM y enlace de Google Maps como URL). Los puertos permitirán el cambio.

## D-013 — Puntualidad ≠ OTIF · **Decidida para la demo (2026-10-13)**
- **Decisión:** se definirán por separado (como exige `DOCS.MD`). Por indicación del usuario, la
  demo no necesita una definición de negocio cerrada: se sembrarán **varios escenarios de
  ejemplo** con distinto cumplimiento (p. ej. 100 %, 90 %, ...), rotulados como datos
  sintéticos de demostración. Se implementará en la fase 3 (ruteo). Hasta entonces el OTIF se
  muestra como "No disponible (requiere ruteo)".
- **Consecuencia:** los porcentajes serán ilustrativos y nunca se presentarán como medición real.

## D-014 — Versión de Python y zona horaria
- `requires-python >= 3.12`, pero el entorno solo tiene 3.13.15: **solo se probó en 3.13**.
- La hora operacional es Bogotá, modelada como UTC−5 fijo (Colombia no tiene horario de verano).

## D-015 — Node instalado localmente, `node_modules` fuera de OneDrive
- **Contexto:** Node no estaba instalado y la prioridad es una demo con frontend. El repositorio
  vive dentro de OneDrive, que sincronizaría miles de archivos de `node_modules`, y las rutas largas
  de Windows (límite de 260 caracteres) ya dieron un fallo real (WinError 206).
- **Decisión:** zip portable de Node LTS (v24.21.0) verificado por SHA-256 en
  `%LOCALAPPDATA%\fleetplanner-tools\node`; `APP/Frontend/node_modules` es una unión hacia
  `%LOCALAPPDATA%\fleetplanner-tools\frontend_node_modules`. Sin cambios en el PATH global ni
  administrador. Reproducible con `scripts/setup-frontend.ps1`.
- **Consecuencia:** hay que ejecutar ese script en una máquina nueva; las versiones del frontend
  quedan fijadas en `package.json` (exactas) y `package-lock.json`.

## D-016 — Sesión: access token en memoria + refresh en cookie HttpOnly
- **Decisión:** access token JWT de 15 min que el frontend guarda solo en memoria; refresh token
  opaco (8 h) en cookie `HttpOnly`, `SameSite=Strict`, ruta `/api/v1/auth` (y `Secure` fuera de
  `local`), con **rotación en cada uso** y revocación de toda la familia si se reutiliza uno ya
  rotado. Cierre de sesión revoca el access token (por su `jti`, hasta que expire) y el refresh.
- **Defensa CSRF adicional:** los endpoints de cookie verifican la cabecera `Origin` contra la lista
  blanca.
- **Consecuencia:** el access token JWT no sirve por sí solo: `AuthenticateRequest` relee usuario,
  rol y empresa en cada solicitud, de modo que un cambio de rol o una suspensión surten efecto de
  inmediato.

## D-017 — Aislamiento de tenant en la demo en memoria
- **Decisión:** el tenant sale únicamente de la `Principal` (token validado + usuario guardado). Los
  esquemas de la API rechazan campos desconocidos (`extra="forbid"`), los endpoints no tienen
  parámetros de tenant y cada empresa recibe su propio `TenantWorkspace` (lector, repositorio de
  resultados y casos de uso). La suspensión se aplica en cada solicitud y revoca sesiones.
- **Limitación:** es aislamiento lógico en memoria dentro de un solo proceso; no demuestra
  aislamiento de infraestructura (tres PostgreSQL) porque la base de datos está comentada (D-001).

## D-018 — Claves de la demo
- **Decisión:** `JWT_SIGNING_KEY` es obligatoria fuera del entorno `local` (la aplicación no
  arranca sin ella). En `local` se genera una clave **efímera** y se avisa en consola: las sesiones
  caducan al reiniciar. Las contraseñas sembradas son aleatorias y se muestran una sola vez en la
  consola del backend; por eso cambian en cada arranque.
- **Consecuencia:** para una demo repetible conviene dejar el backend en marcha; reiniciarlo exige
  anotar de nuevo las contraseñas.

## D-019 — Exportación CSV en el cliente
- **Decisión:** para la demo, el CSV del tablero se genera en el navegador con neutralización de
  fórmulas (`=`, `+`, `-`, `@`, tab y retorno de carro al inicio) y BOM UTF-8 para Excel. Excel
  nativo (`.xlsx`) queda pendiente.
- **Consecuencia:** la exportación depende de datos que ya autorizó el backend; en producción se
  recomienda generarla en el servidor, con auditoría.
