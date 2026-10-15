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

## D-020 — Dependencias nuevas aprobadas (2026-10-14)
- **Contexto:** el usuario aprobó el plan de las fases restantes y estas dependencias.
- **Decisión:** `leaflet 1.9.4` y `@types/leaflet 1.9.22` (mapa con OpenStreetMap, sin API key;
  instaladas, versión exacta, 0 vulnerabilidades). Aprobadas **pero aún no instaladas**:
  `scikit-learn` (ML), `openpyxl` (Excel en servidor), `playwright` (E2E).
- **Consecuencia:** las teselas vienen de los servidores públicos de OSM (atribución visible, uso
  moderado). Para producción se usaría un proveedor de teselas propio.

## D-021 — Las propuestas de re-ruteo siempre esperan al despachador
- **Contexto:** `DOCS.MD` §7.5 exige confirmación solo si el cambio afecta a más de un vehículo o
  activa reserva/tercero; el sistema "propone".
- **Decisión:** en la demo **toda** propuesta con cambios queda pendiente hasta que el despachador la
  apruebe o rechace (más estricto que el mínimo). La bandera `requires_confirmation` indica cuándo
  la confirmación es obligatoria según la especificación. Al crearse una propuesta pendiente el
  reloj simulado se **pausa**, para que no quede obsoleta mientras se lee.
- **Obsolescencia:** si el plan cambió (otra versión) o el reloj avanzó más de 5 min desde que se
  calculó, aprobarla **no se aplica a ciegas**: queda `obsoleta`, se recalcula con la situación actual
  y hay que confirmar de nuevo.
- **Consecuencia:** no hay re-ruteos automáticos. El seguimiento (`TrackFleet`) solo propone.

## D-022 — Modelo del plan versionado y congelamiento
- **Decisión:** una versión guarda las **decisiones** (secuencias por vehículo) y los horarios al
  crearla; es inmutable y las versiones son consecutivas (el repositorio rechaza saltos o
  repeticiones). Los horarios "reales" se **proyectan** reevaluando las secuencias con lo que se sabe
  hoy (cierres, ventanas nuevas). Lo entregado o en servicio se congela; un vehículo en tránsito se
  replanifica desde su posición interpolada. Una carga solo cambia de vehículo con transbordo
  (avería, 25 min) o recarga en el CEDI (urgente, 20 min).
- **Pedido urgente:** se compara, por vehículo en ruta, volver al CEDI a recargar (en cada posición
  posible) contra activar una reserva/tercero (con un costo de activación en puntos del puntaje; el
  tercero cuesta el doble). Es viable solo si cumple capacidad y la ventana del urgente. Si ninguna
  opción lo es, se propone aplazarlo al día siguiente y se alerta.
- **Consecuencia:** el seguimiento y los indicadores usan la misma proyección que la torre de control.

## D-023 — Cierres viales
- **Decisión:** un cierre afecta un tramo si su radio toca el origen, el destino o el punto medio y
  el cierre está activo a la hora de salida del tramo (no a la de llegada). Con varios cierres
  aplica el **mayor** factor (no se multiplican). Empieza al registrarse el evento.
- **Limitación:** el punto medio es en línea recta; un tramo largo podría rozar el cierre sin que
  los tres puntos caigan en el radio.

## D-024 — Motores del plan de la mañana
- **Decisión:** se ejecutan OR-Tools y la heurística (arrepentimiento + 2-opt + reubicación) sobre el
  mismo problema; se descarta el plan que viole capacidad y se elige el de menos pedidos sin asignar
  y, a igualdad, menor puntaje. El plan guarda el puntaje de ambos. El puntaje lo calcula siempre el
  evaluador de dominio.
- **Hallazgo:** con la matriz de tiempos a las 06:00 el solver subestimaba los viajes (velocidades más
  altas) y quedó peor que la heurística (1159,8 vs 738,4). Se calcula a arranque + 3 h (media
  jornada) y el solver pasó a ganar (≈706 vs 738). No se afirma que gane siempre.
- **Consecuencia:** el límite del solver es 2,5 s y 4000 soluciones (reproducible); crear el día
  tarda ~3,4 s.

## D-025 — Indicadores diarios
- **Decisión (D-013 aplicada):** puntualidad = entregados dentro de ventana / comprometidos; OTIF =
  entregados completos y a tiempo / comprometidos. El denominador es el mismo siempre: todos los
  pedidos del día, incluidos los urgentes y los sin atender (cuentan como no cumplidos). Puntual =
  llegada ≤ fin de ventana.
- **Escenarios:** se ejecutan en un espacio de trabajo aparte con el mismo guion de cuatro eventos
  (cierre 08:15 en la Calle 80, cambio de ventana 09:30, urgente 10:30, avería 11:00). El estático
  aplica los mismos eventos sin re-rutear. Las "entregas incompletas" son un **parámetro de ejemplo**
  (cada décima entrega), no una medición.
- **Hallazgo honesto:** el ruteo dinámico entrega más pedidos pero puede registrar más entregas
  tarde, porque atiende pedidos que el plan estático nunca atendió y algunos llegan fuera de ventana.
  La pantalla lo explica.

## D-026 — Proveedor de tiempos simulado y respaldo
- **Decisión:** `SimulatedTrafficProvider` (DEMO-ONLY) usa Haversine × 1,35, el perfil de velocidades
  y una congestión "en vivo" inventada por hora; puede "caerse" a pedido. El respaldo
  (`SpeedProfileTimeEstimator`) usa solo el perfil y los cierres conocidos, y la interfaz muestra
  **"Tiempos estimados sin tráfico"**. Nunca se afirma tráfico en vivo.

## D-027 — Ventanas que cruzan la medianoche
- **Decisión (cierra la duda de `DOCS.MD` §8 para la demo):** no se aceptan; se rechazan con un
  mensaje que pide dividir la ventana o corregir las horas. Una ventana invertida (14:00–10:00) se
  trata igual. Cualquier cambio a aceptarlas requiere decisión de negocio.

## D-028 — GPS simulado, geocerca y pérdida de señal
- **Decisión:** `SimulatedGps` (DEMO-ONLY) detrás de `GpsPort`: cada vehículo reporta una lectura
  cada 2 min simulados (configurable de 1 a 5) con la posición que dicta el plan; las lecturas se
  generan al consultar (se ponen al día hasta la hora del reloj, con tope de 300 min). Se puede cortar
  la señal de un vehículo; la última lectura envejece.
- **Geocerca:** entrega confirmada si el vehículo permanece a ≤ 100 m del cliente MÁS de 5 min
  seguidos (salir del círculo reinicia la cuenta). La confirmación se registra con su fuente
  (`geofence`) y **la primera confirmación gana**; la evalúa el seguimiento y también la consulta de
  la torre de control (idempotente).
- **Sin señal:** si la última lectura tiene más de 15 min de antigüedad se alerta con esa antigüedad y
  **se conserva el plan** (no se re-planifica). Vehículos que no han salido, ya terminaron o están en
  espera no se consideran sin señal.
- **Limitación:** la posición histórica se calcula con el plan vigente, no con el plan de ese
  momento; es una aproximación aceptable para la demo.

## D-029 — Seguimiento programado y tiempo real (SSE)
- **Decisión:** una tarea programada (cada 2,5 s, arrancada con la API) ejecuta el seguimiento de cada
  empresa con un día en curso. El contexto de tenant sale del registro central
  (`TenantWorkspaceCatalog`), no de una solicitud; se omiten empresas suspendidas y días en pausa, y un
  fallo en una empresa se audita y no frena a las demás.
- **SSE:** `GET /api/v1/routing/stream` con `fetch` y `Authorization` (no `EventSource`). Se autoriza
  **antes** de abrir el flujo (sin permiso: 403) y se revalida identidad, rol y empresa activa en
  cada evento. La conexión se cierra cada 55 s (el cliente reconecta con el token renovado) y hay un
  máximo de 4 por usuario. Si el flujo falla 3 veces la pantalla vuelve a consultar cada 2,5 s.
- **Hallazgo corregido:** las pruebas mostraron que los roles sin permiso recibían HTTP 200 porque la
  autorización ocurría dentro del generador, con la respuesta ya iniciada.

## D-030 — Hoja de ruta del conductor
- **Decisión:** el vehículo del conductor sale de `User.attributes["vehicle_id"]` (registro central) y
  viaja en la `Principal`; ningún parámetro de la solicitud puede cambiarlo (los esquemas rechazan
  `vehicle_id`). Sin vehículo asignado: 403 y auditoría.
- **Confirmar entrega:** solo si el vehículo ya llegó a la parada (según el plan); idempotente; si
  la geocerca ya la confirmó se informa y no se sobrescribe. Queda a nombre del conductor.
- **Novedades:** (cliente ausente, acceso bloqueado, mercancía dañada, problema del vehículo, otra)
  de 3 a 300 caracteres, con límite de 20 por minuto. **No cambian el plan**: avisan al despachador
  (alerta; crítica si es del vehículo).
- **Navegación:** enlaces `https://www.google.com/maps/dir/?api=1&…` sin clave ni API; hasta 9
  puntos intermedios por enlace y, si hay más paradas, enlaces encadenados. Solo incluyen las paradas
  pendientes.

## D-031 — Maestros guiados por esquema; el dominio es la única fuente de validez
- **Contexto:** hay varios maestros con campos, unidades y reglas distintas; duplicar validaciones en la API y
  el frontend las desalinearía.
- **Decisión:** un esquema de dominio (`EntitySpec/FieldSpec`) describe cada maestro; la API lo publica y la
  interfaz arma tablas y formularios a partir de él. Para validar, el servicio construye el objeto de
  dominio real con sus constructores (por ejemplo, un cliente con latitud 40 o ventana 14:00–10:00 se
  rechaza con la misma explicación del criterio 11). Los errores de Python se traducen a mensajes en
  español.
- **Integridad referencial:** no se borra un registro que otro referencia (409 con el motivo). La clave no
  se edita.
- **Lectura por el negocio:** el tablero de capacidad y el ruteo leen los maestros editables (lectores
  respaldados por el almacén); con la siembra reproducen los resultados originales (probado). El ruteo
  recarga los maestros al iniciar el día operativo, no a mitad de día. Solo el administrador de empresa
  accede (deniega por defecto); la empresa sale de la identidad autenticada.
- **Consecuencia:** agregar un maestro es agregar su especificación y su constructor, no pantallas nuevas.

## D-032 — Carga CSV con previsualización, todo o nada
- **Decisión:** límite de 200 KB y 5000 filas (la ruta de carga admite 256 KB de cuerpo; el resto de la API
  64 KB), separador `,` o `;`. La previsualización no escribe nada y lista errores con fila y columna; solo
  se puede aplicar si no hay errores y se aplica en bloque (todo o nada). Los textos que empiezan como
  fórmula (`=`, `+`, `-`, `@`) se rechazan.
- **Consecuencia:** una carga parcial nunca deja datos a medias; el historial registra cada alta/cambio.

## D-033 — Parámetros versionados con vigencia e historial solo-agregar
- **Decisión:** cada parámetro (reserva, días operativos por mes, hora de salida…) conserva versiones con
  valor, vigencia, usuario, fecha y motivo. Se permite una vigencia futura (queda "programada"); el pasado
  no se reescribe. El historial de cambios es solo-agregar y guarda antes/después. Los cambios invalidan el
  caché de indicadores mediante escuchas (`on_change`).
- **Consecuencia:** para saber qué valor regía un día basta consultar las versiones.

## D-034 — Exportaciones en el servidor (Excel y CSV)
- **Decisión:** `SpreadsheetExporterPort` con un adaptador openpyxl (dependencia aprobada en D-020).
  Los textos que parecen fórmula se neutralizan con apóstrofo y tipo de celda texto; los nombres de archivo
  se sanean; cada exportación se audita (`RecordExport`). Se exportan el tablero de capacidad, cada maestro y
  la hoja del conductor (solo la suya).
- **Pendiente:** generación en segundo plano para volúmenes grandes.

## D-035 — ML detrás de puertos, un servicio por empresa y generador sintético
- **Contexto:** `DOCS.MD` §13 pide cuatro casos de ML con adaptadores scikit-learn, entrenados por tenant
  y sin que el dominio conozca la librería.
- **Decisión:** puertos `DemandForecaster`, `AnomalyDetector`, `DelayRiskPredictor`, `PatternMiner`,
  `HistoryReaderPort` y `ModelRegistryPort`; adaptadores en `adapters/outbound/ml`; tipos propios en
  `domain/ml`. Cada empresa recibe su propio `MlService`, lector y registro al crear su espacio de trabajo,
  así que no hay operación que mezcle datos.
- **Datos:** el generador (DEMO-ONLY) usa los corredores y clientes de la empresa y siembra patrones
  conocidos para poder probar que los modelos los encuentran. Las métricas se declaran **de este fixture**.
- **Dependencia (aprobada en D-020):** `scikit-learn==1.9.1` (con `scipy`, `joblib`, `threadpoolctl`,
  `narwhals`, `cloudpickle`, fijadas en `requirements.lock`) por ser la librería pedida por el documento
  maestro y ya instalable sin servicios externos.
- **Consecuencia:** un modelo nuevo es un puerto/adaptador más; el caso de uso no cambia.

## D-036 — Artefactos de ML con hash verificado antes de cargar
- **Decisión:** los artefactos son `pickle` producidos por el adaptador, guardados con su SHA-256; el
  registro recalcula el hash y, si no coincide con el registrado, lanza `ArtifactIntegrityError` y no
  deserializa. No se acepta ningún archivo de ML que venga de un usuario.
- **Riesgo aceptado y declarado:** `pickle` es inseguro con datos no confiables; aquí el origen es el propio
  proceso y el hash protege contra alteración del almacén, pero **no** contra un atacante que controle a la
  vez el artefacto y el registro. Bandit B403/B301 quedan suprimidos con esta justificación.
- **Deuda:** formato sin ejecución de código (p. ej. `skops` u ONNX) y firma del registro al pasar a
  persistencia real (`docs/DEUDA_DEMO.md`).

## D-037 — Cómo se usan los resultados de ML
- **Tablero de capacidad:** muestra el pronóstico ML frente al percentil histórico, **pero no reemplaza** la
  demanda de diseño del balance (que sigue usando el percentil, D-005). Si el ML falla por datos
  insuficientes o por integridad, el tablero sigue funcionando y lo advierte.
- **Primer uso entrena** (unos 2–3 s por empresa); el reentrenamiento programado nunca entrena en frío.
- **Permisos:** leer patrones (`patterns:read`) = gerencia y despachador; reentrenar (`patterns:train`) =
  solo gerencia, con límite de 3 por minuto y auditoría de las versiones resultantes. El administrador de la
  empresa no accede (mínimo privilegio).
- **Lenguaje:** las anomalías son asociaciones estadísticas, el riesgo de retraso es una estimación y los
  segmentos una descripción; la interfaz lo dice y muestra la procedencia (versión, fecha, huella, métricas).
- **Pendiente:** conectar el riesgo de retraso con la propuesta de re-secuenciación del ruteo.

## D-038 — Demo compartida: un proceso, contraseñas por entorno
- **Contexto:** el usuario quiere mostrar la demo desde otro PC o un celular fuera de su red (Railway o
  su propio PC con un túnel).
- **Decisión:** (1) la API sirve la interfaz compilada (`FRONTEND_DIST`) desde el mismo origen, registrada
  al final para no tapar `/api`; no hay CORS ni Vite en este modo. (2) Las contraseñas de los usuarios
  sembrados pueden fijarse con `DEMO_PASSWORD` y `DEMO_SUPERADMIN_PASSWORD` (≥ 12 caracteres, distintas,
  fuera de Git, nunca impresas ni en `repr`); sin ellas siguen siendo aleatorias. (3) CSP distinta para la
  interfaz (scripts propios, estilos en línea de Leaflet/React, teselas de OpenStreetMap) y estricta para
  `/api`. (4) El origen de `login`/`refresh` se acepta si coincide con el propio host cuando se sirve la
  interfaz, para no depender de configurar `ALLOWED_ORIGINS` en el hospedaje.
- **Riesgo aceptado:** una contraseña compartida entre roles, adecuada solo para una presentación; quien la
  tenga puede reiniciar el día y reentrenar, y el estado es único y compartido.
- **No verificado:** imagen Docker (no hay Docker local), SSE a través de un proxy real, revisión visual en
  celular.

