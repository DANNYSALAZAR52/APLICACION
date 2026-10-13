# Especificación funcional y técnica de la aplicación de logística

**Documento maestro del producto.** Esta especificación define el alcance, las reglas de negocio, los algoritmos, la arquitectura, los controles de calidad y los criterios de aceptación de una aplicación de planeación de flota y ruteo dinámico. Los documentos `docs/ESPECIFICACIONES_BACKEND.md`, `docs/ESPECIFICACIONES_FRONTEND.md` y el archivo `CLAUDE.md` complementan esta especificación; no la reemplazan.

## 1. Propósito y principios

Se construirá una demo funcional para una empresa de transporte. La demo debe permitir mostrar a un cliente que la solución es viable y, al mismo tiempo, dejar una base técnica mantenible sobre la que pueda evolucionar el producto real.

Principios obligatorios:

- El dominio y los casos de uso se diseñan con criterios de producción, aunque existan adaptadores simulados en la demo.
- Todo elemento exclusivo de la demo —datos sintéticos, GPS simulado, proveedor de tráfico simulado y atajos temporales— debe quedar detrás de un puerto/adaptador reemplazable, marcado `DEMO-ONLY` y registrado en `docs/DEUDA_DEMO.md`.
- La interfaz, la documentación y los mensajes al usuario estarán en español. Los identificadores de código, clases, funciones, variables y tablas estarán en inglés.
- Todos los datos de la demo deben identificarse claramente en la interfaz como **DATOS DE DEMOSTRACIÓN**. Nunca se presentan datos sintéticos como observaciones reales.
- No se inventan resultados de pruebas, métricas, controles de seguridad o comandos ejecutados. Se informa de manera explícita qué se ejecutó, qué pasó, qué falló y qué no se pudo ejecutar.
- El sistema recomienda y propone acciones; no compra vehículos, contrata terceros ni aplica cambios operativos de alto impacto sin la aprobación humana definida en esta especificación.
- Se prioriza una entrega vertical funcional y demostrable por fase, antes que generar grandes volúmenes de código sin integrar.

## 2. Convenciones, nombres y estructura del repositorio

El nombre de una empresa usada en el demo no debe convertirse en nombre del producto ni quedar incrustado en identificadores, rutas, código o documentación. Se usarán nombres genéricos como **Empresa Demo A** y **Empresa Demo B** para distinguir tenants. La aplicación se denominará simplemente **la aplicación**.

Estructura objetivo en la raíz del repositorio:

```text
.
├── APP/
│   ├── Backend/
│   └── Frontend/
├── infra/
├── docs/
├── DOCS.MD
├── CLAUDE.md
├── PROMPT_INICIAL.txt
├── .env.example
├── .gitignore
└── Makefile
```

La carpeta `APP/Backend` contiene la API, dominio, casos de uso, adaptadores y pruebas de backend. `APP/Frontend` contiene la aplicación React. `infra/` contiene Docker Compose, proxy, certificados locales de desarrollo y scripts de infraestructura. `docs/` contiene los documentos técnicos, las decisiones, los informes y los registros de avance.

Se puede refinar la estructura interna, pero no se debe fusionar backend y frontend ni moverlos fuera de `APP/`. Las rutas de Docker Compose, scripts y CI deben coincidir con esta estructura real; no deben copiar rutas de estructuras antiguas.

## 3. Usuarios, módulos y alcance

### 3.1 Usuarios

- **Gerencia de operaciones:** análisis y planeación de capacidad de flota.
- **Despachador:** torre de control, eventos y aprobación de propuestas de re-ruteo.
- **Conductor:** consulta de hoja de ruta, confirmación de entregas y reporte de novedades.
- **Administrador del tenant:** maestros, parámetros, usuarios y carga de datos de su empresa.
- **Superadministrador:** administración y aprovisionamiento de tenants. Es el único rol que ve la pantalla de administración de clientes.

### 3.2 Módulo 1: capacidad de flota

Responde cuántos vehículos necesita una empresa hoy y en los próximos cinco años, por tipo de vehículo, considerando flota propia y de terceros. Incluye métodos de balance, Lean, Monte Carlo, optimización del mix y decisión de flota propia/tercerizada. Los resultados son recomendaciones para apoyar decisiones; nunca generan por sí mismos compras o contratos.

### 3.3 Módulo 2: ruteo dinámico

Planifica cada mañana la operación urbana de distribución para los vehículos disponibles y las órdenes pendientes. Durante la operación simula la ubicación GPS y permite recalcular rutas ante un cierre vial, pedido urgente, cambio de ventana horaria o avería. Cada recálculo guarda una nueva versión del plan, con motivo y trazabilidad.

### 3.4 Requisitos transversales obligatorios

- Arquitectura hexagonal estricta y principios SOLID demostrables con código y pruebas.
- Multi-tenancy con una base de datos por empresa cliente, con posibilidad de que cada base esté en un servidor distinto.
- Cuatro casos de uso de ML en el backend: pronóstico de demanda, detección de anomalías, riesgo de retraso y segmentación.
- Controles de seguridad alineados con OWASP Top 10 2021, pruebas de seguridad y un informe honesto de estado.
- Datos sintéticos reproducibles, reloj inyectable y simulación desacoplada de los casos de uso.
- Aplicación responsive, con vista de escritorio y hoja de ruta utilizable en celular.

### 3.5 Fuera del alcance de la demo

Dejar puertos e interfaces donde corresponda, documentar en `docs/ROADMAP.md` y no simular una integración real:

- Integración real con un proveedor de GPS.
- Integración real con Google Routes, Geocoding o Route Optimization API.
- Integraciones directas con ERP, TMS o CRM.
- Facturación, nómina, mantenimiento vehicular y pagos.
- Aplicación nativa de navegación.
- MFA/TOTP completo, que quedará señalado como pendiente de la versión productiva.
- Compra automática de servicios externos o uso de credenciales de pago.

El demo debe usar OpenStreetMap/Leaflet y enlaces de navegación a Google Maps construidos con el formato oficial de URL, sin llamar a APIs de pago.

## 4. Guion del demo

El flujo completo debe poder presentarse en aproximadamente 10 minutos. Documentarlo en `docs/DEMO_GUION.md` con pasos, usuario de demostración, pantalla esperada y resultado verificable.

1. Iniciar sesión como gerencia en Empresa Demo A y mostrar que Empresa Demo B tiene datos separados.
2. Mostrar tablero de capacidad: balance, Lean, Monte Carlo, optimización de mix y propio vs. tercero; brecha por tipo; proyección a cinco años en tres escenarios; KPI y pronóstico de ML con intervalo.
3. Abrir “Patrones detectados” y mostrar anomalías de espera, segmentos de clientes y riesgo de retraso.
4. Cambiar a despachador: torre de control, mapa, vehículos moviéndose con GPS simulado y reloj acelerado, paradas completadas/pendientes y entregas en riesgo.
5. Inyectar uno de cada tipo de evento: cierre vial, pedido urgente, cambio de ventana y avería. Mostrar propuesta, motivo, impacto y botones para aprobar o rechazar; comparar versiones del plan.
6. Abrir la hoja de ruta del conductor en vista celular y probar el enlace a Google Maps.
7. Mostrar indicadores del día y comparar plan estático contra ruteo dinámico.
8. Mostrar el informe OWASP, el estado de los controles y evidencia del aislamiento entre tenants.
9. Mostrar la pantalla de administración de tenants con el usuario superadministrador.

## 5. Modelo de datos

Motor de datos: PostgreSQL 16 + PostGIS. Redis se usa para la caché de matrices de tiempos con vencimiento de 15 minutos. Separar los modelos ORM de las entidades de dominio mediante mapeos explícitos. Las tablas transaccionales y de maestros aplicarán auditoría de acuerdo con su naturaleza. Como regla general tendrán `id`, `created_at`, `updated_at` y `updated_by`; las tablas append-only, datos de alta frecuencia y registros de auditoría deben documentar cualquier excepción y conservar trazabilidad sin permitir sobrescrituras indebidas.

### 5.1 Maestros

1. `vehicle_type`: nombre, capacidad en toneladas, capacidad en m³, pallets, costo fijo mensual, costo variable por km, tarifa diaria de tercero.
2. `vehicle`: placa, tipo, condición propio/tercero, identificador GPS, activo.
3. `customer`: código único, nombre, dirección, latitud, longitud, minutos de servicio, ventana inicial/final y restricciones.
4. `corridor_route`: código, nombre, tipo de vehículo asignado, km de ida, velocidad promedio, horas operativas, tiempo de cargue, espera en muelle, número de paradas, minutos por parada, espera de cliente, porcentaje de llenado y porcentaje de backhaul.
5. `compatibility`: ruta, tipo de vehículo y si la combinación está permitida.

### 5.2 Parámetros y escenarios

6. `parameter`: clave, valor, unidad y fecha de vigencia. Los cambios generan historial: no se sobrescribe el valor previo sin conservarlo. Ejemplos: percentil de diseño `0.90`, reserva `0.08` y días al mes `26`.
7. `speed_profile`: hora del día (0–23) y velocidad en km/h. Es el respaldo cuando el proveedor de tiempos no está disponible.
8. `growth_scenario`: nombre, CAGR, ajustes por ruta, volumen nuevo y año de entrada. La interpretación del volumen nuevo (adición anual recurrente o incremento único) debe documentarse y validarse con el responsable de negocio antes de cerrar los cálculos definitivos.

### 5.3 Transaccionales

9. `daily_demand`: fecha, ruta y toneladas. Un día sin observación es dato ausente, no demanda cero.
10. `order`: fecha, cliente, kg, m³, ventana inicial/final, prioridad y estado: pendiente, asignado, entregado, tarde o no entregado. Debe existir un identificador de pedido y no repetirse en el mismo día.
11. `gps_position`: vehículo, fecha/hora, latitud, longitud, velocidad y estado de motor. Las ubicaciones se retienen y registran conforme a la política de privacidad y retención definida.
12. `event`: tipo (cierre, pedido urgente, cambio de ventana, avería), fecha/hora, datos JSON y usuario que lo registró.

### 5.4 Resultados y caché

13. `route_plan`: versión, fecha operativa, vehículo/ámbito de planificación, estado, fecha de creación, creador y motivo de generación. No se borra ni sobrescribe una versión anterior de un plan.
14. `plan_stop`: plan/version, orden de secuencia, cliente/pedido, llegada estimada, inicio de servicio, salida, retraso en minutos, estado y motivo de cambio.
15. `capacity_result`: fecha de corrida, método, tipo de vehículo, año, flota requerida y parámetros usados en JSON.

La matriz de tiempos se cachea en Redis con TTL de 15 minutos. Si no hay caché o el proveedor no responde, se utiliza el adaptador de respaldo correspondiente y se informa la condición al usuario.

## 6. Módulo 1: reglas de capacidad de flota

Cada cálculo debe poder ejecutarse desde un caso de uso, ser reproducible y guardar entradas/parámetros y resultados. Las fórmulas críticas deben vivir en el dominio, ser puras cuando aplique y probarse con ejemplos calculados manualmente.

### P1. Demanda de diseño por ruta

Usar hasta los últimos 60 días disponibles. Calcular promedio, desviación estándar y percentil de diseño (P90 por defecto). El dimensionamiento se basa en el percentil, no únicamente en el promedio. Los días sin datos permanecen ausentes y no se convierten en cero. Informar cuántos días válidos entraron al cálculo.

### P2. Ciclo de viaje y capacidad efectiva

```text
ciclo_h = tiempo_cargue
        + espera_muelle
        + 2 * (km_ida / velocidad)
        + (paradas * min_parada / 60)
        + espera_cliente
viajes_dia = horas_operativas / ciclo_h
OEE = disponibilidad * utilizacion * rendimiento
capacidad_efectiva_t_dia = capacidad_t * pct_llenado * viajes_dia * OEE
```

Porcentajes se normalizan internamente a fracciones entre 0 y 1. Validar que el ciclo, velocidad, capacidad y horas sean positivos y que los factores de OEE estén dentro del rango permitido. Evitar división por cero e informar datos insuficientes o inconsistentes.

### P3. Flota requerida por balance

Para cada ruta y tipo de vehículo permitido:

```text
vehiculos_ruta = demanda_diseno_ruta / capacidad_efectiva_ruta_tipo
```

Aplicar la reserva, agregar por tipo de vehículo y redondear hacia arriba en el punto correcto de agregación, evitando tanto subestimar como redondear cada fracción de manera que infle injustificadamente el total. La lógica y el orden de redondeo deben quedar documentados y cubiertos por pruebas. La brecha es `flota_actual - flota_requerida`; un valor negativo representa déficit.

### P4. Proyección a cinco años

Escenarios: base, optimista y pesimista. Para año `n`:

```text
tasa_ruta = CAGR + ajuste_ruta
demanda_n = demanda_diseno * (1 + tasa_ruta)^n + volumen_nuevo_aplicable
```

Repetir P3 para cada año y escenario. Mostrar el primer año en el que la flota requerida supera la flota actual. La definición temporal de `volumen_nuevo_aplicable` es un punto explícito que debe resolverse con negocio y registrarse en `docs/DECISIONES.md` antes de usar datos productivos.

### P5. Flota Lean

Recalcular el ciclo con metas de reducción en tiempo de muelle, cargue, parada y espera de cliente. Usar demanda promedio multiplicada por el colchón Heijunka.

```text
flota_lean = (viajes_requeridos * ciclo_estandar)
             / (horas_operativas * OEE_objetivo)
```

Calcular también:

- `% valor agregado = tránsito cargado / ciclo`.
- `% muda = (esperas + retorno vacío) / ciclo`.
- `takt de despacho = minutos operativos / viajes requeridos`.

Mantener unidades consistentes, evitar división por cero y hacer editables los parámetros de metas Lean.

### P6. Monte Carlo

Ejecutar 1.000 días o escenarios simulados con una semilla fija configurable y guardar esa semilla para reproducir resultados. La demanda se genera a partir del promedio y la desviación histórica de cada ruta. El ciclo incluye variación con coeficiente de variación del 10 %.

Como las distribuciones normales pueden producir demanda o factores de ciclo negativos, la implementación debe usar una distribución positiva apropiada o una normal truncada/restringida con regla documentada. Nunca permitir capacidades negativas ni divisiones por valores no positivos. Redondear la flota requerida hacia arriba en cada simulación. Reportar P50, P90, P95 y porcentaje de días en que la flota actual cubre la demanda.

### P7. Optimización del mix de flota

Usar programación lineal entera mixta con OR-Tools o PuLP. Minimizar costos fijos y variables sujeto a capacidad, demanda y compatibilidad. Definir variables de asignación por ruta y tipo (`x[r,t]`) y cantidad total disponible por tipo (`y[t]`). Restricciones mínimas:

```text
sum_t(capacidad[r,t] * x[r,t]) >= demanda[r] * (1 + reserva)
sum_r(x[r,t]) <= y[t]
x[r,t] = 0 cuando la combinación ruta/tipo no es compatible
x[r,t], y[t] son enteras no negativas
```

El objetivo incluye costo fijo por vehículo disponible y costo variable de operación por asignación. La solución debe tener estado verificable (óptima, factible, inviable, límite de tiempo, etc.); nunca mostrar una solución incompleta como óptima. Definir límites de tiempo y tamaño del problema.

### P8. Flota propia vs. terceros

La versión inicial contempla una comparación de costos diarios a partir de la demanda histórica de vehículos requeridos `R`:

```text
costo(N) = N * costo_fijo_diario
         + costo_variable_propio_de_vehiculos_utilizados
         + tarifa_tercero_diaria * promedio(max(R - N, 0))
```

La fórmula se debe llevar a un modelo coherente con tipos de vehículo, capacidades, compatibilidad y costos por tipo; una sola variable total `N` no basta para garantizar la mezcla de turbos, sencillos, doble troque y tractomulas. Convertir costos mensuales a diarios con los días configurados y calcular el componente variable según los km/uso modelados, sin duplicar costos. No usar un rango fijo de `N=0..40`: derivar el límite de búsqueda de la demanda histórica y de la capacidad del modelo, incluyendo margen suficiente para cubrir soluciones factibles. Reportar el costo mínimo, composición óptima y comparación con escenarios alternativos.

### P9. Tablero de capacidad

Mostrar métodos lado a lado, flota requerida por tipo, brecha, uso de supuestos y fecha de cálculo. KPI mínimos: utilización, OEE, porcentaje de llenado, porcentaje de km en vacío, costo por tonelada-km, costo por tonelada y puntualidad/OTIF según la definición aprobada. Incluir hallazgos explicables y advertir si hay datos insuficientes, supuestos aplicados o resultados de ML no disponibles. El módulo corre por tarea nocturna o botón “Recalcular”; no depende de GPS en tiempo real ni de Google.

## 7. Módulo 2: ruteo dinámico

### 7.1 Distancias y tiempos

- En el prototipo: distancia Haversine multiplicada por 1,35 como aproximación de distancia vial. Debe estar encapsulada en el adaptador y marcada `DEMO-ONLY`.
- En producción: un adaptador de `TrafficTimePort` devolverá distancias/tiempos de proveedor real, sin modificar dominio ni casos de uso.
- Tiempo: `km / velocidad_de_la_hora_de_salida * 60`, según `speed_profile`.
- Si existe un cierre activo cuyo radio afecta el origen, destino o punto medio del tramo, multiplicar el tiempo por el factor del evento.
- Si el proveedor simulado no responde, usar `speed_profile` y mostrar “Tiempos estimados sin tráfico”. No afirmar que hay información de tráfico en vivo.

### 7.2 Ventanas, servicio y carga

Para cada parada:

```text
llegada = salida_anterior + tiempo_de_viaje
inicio_servicio = max(llegada, inicio_ventana)
retraso = max(llegada - fin_ventana, 0)
salida = inicio_servicio + minutos_servicio
```

Para el ejemplo, `minutos_servicio = 15 + kg/50`, parametrizable. La carga inicial corresponde a la suma de los pedidos del vehículo; disminuye después de cada entrega y nunca supera `capacidad * llenado_maximo`. Ejemplo de referencia: turbo de 4.500 kg con llenado máximo del 90 % tiene capacidad operativa de 4.050 kg.

El puntaje del plan que se minimiza es:

```text
minutos_viaje
+ 0.2 * minutos_espera
+ 20 * minutos_retraso
+ 2 * minutos_despues_fin_turno
```

Los pesos deben ser parámetros editables/versionados. Un plan que viola capacidad se descarta. Asegurar coherencia con las unidades y no comparar soluciones con objetivos diferentes sin indicarlo.

### 7.3 Plan diario

A las 05:00 se leen órdenes pendientes, coordenadas y vehículos disponibles; se prepara una matriz de tiempos CEDI-clientes con hora de salida de referencia 06:00. Construir una solución mediante OR-Tools (VRP con ventanas horarias y capacidad). Implementar también la heurística de inserción por arrepentimiento, 2-opt y reubicación como comparación, sin prometer que una heurística siempre supera al solver. Guardar el plan inicial como versión 1 y generar una hoja de ruta por conductor.

### 7.4 Seguimiento

En producción el seguimiento será cada 10–15 minutos; en la demo, cada intervalo simulado configurable. Leer la posición más reciente a través de `GpsPort`. Una entrega puede marcarse por geocerca aproximada de 100 m mantenida por más de 5 minutos, o por confirmación del conductor. Recalcular horarios de paradas pendientes y, si una parada queda en riesgo, proponer re-secuenciación para ese vehículo y alertar al despachador.

El reloj debe inyectarse mediante `ClockPort` con implementaciones de reloj real y simulado, para mantener deterministas los casos de uso y las pruebas.

### 7.5 Respuesta a eventos

- **Cierre/congestión:** recalcular los tiempos afectados y re-secuenciar vehículos que usan los tramos relevantes.
- **Cambio de ventana:** actualizar la ventana y re-secuenciar el vehículo que transporta el pedido.
- **Pedido urgente:** comparar su inserción en un vehículo en ruta con retorno al CEDI para cargarlo frente a activar reserva. Elegir el costo viable menor; si ninguna alternativa cumple capacidad y ventana, dejar el pedido para el día siguiente y alertar.
- **Avería:** asignar vehículo de reserva o tercero al punto de avería, modelar transbordo de 25 minutos y optimizar las entregas pendientes desde ese punto.

Reglas obligatorias:

- Una parada ya cargada no cambia de vehículo durante el día salvo que exista transbordo o recarga en el CEDI.
- El sistema propone; el despachador confirma los cambios que afecten a más de un vehículo o activen una reserva/tercero.
- Cada re-ruteo crea una nueva versión. No se borra ni sobrescribe la versión anterior.
- Guardar el motivo del cambio (por ejemplo, “cierre vial” o “pedido urgente”), usuario, fecha y decisión de aprobación/rechazo.
- Si un GPS no reporta por más de 15 minutos simulados o reales según el reloj activo, marcar “sin señal”, conservar el último plan y generar alerta. Mostrar la antigüedad de la última posición.

## 8. Validaciones de datos

La aplicación debe rechazar entradas inválidas con un mensaje en español que indique qué corregir:

- Latitud entre -4,3 y 13,5 y longitud entre -82 y -66 para la validación geográfica inicial de Colombia. Un cliente fuera de Bogotá en una ruta urbana se marca para revisión; no se elimina silenciosamente.
- La ventana final debe ser posterior a la inicial. Definir explícitamente tratamiento de ventanas que cruzan medianoche si se habilitan; no aceptarlas implícitamente.
- Kg, m³ y minutos de servicio deben ser positivos cuando correspondan al tipo de operación; las excepciones deben tener una regla explícita.
- Código de cliente único y código de pedido no repetido en el día.
- Porcentajes de llenado, OEE y reserva en el rango 0–100 % en la entrada; normalizados a fracciones internamente.
- Velocidades entre 5 y 90 km/h para la configuración del prototipo.
- La carga no supera `capacidad * llenado_maximo`.
- Solo se permiten combinaciones ruta/tipo configuradas como compatibles.
- Cada pedido se asigna a una sola ruta/vehículo; si no existe solución factible, queda “sin asignar” con razón legible.
- Validar CSV/Excel por esquema, tipo, tamaño, columnas y valores. Al exportar a hojas de cálculo, neutralizar celdas que comiencen por `=`, `+`, `-` o `@` para reducir riesgo de inyección de fórmulas.
- Un pedido es puntual si la llegada al cliente ocurre antes o en el fin de ventana, sujeto a la definición aprobada de la regla de negocio.

### Definiciones de KPI

No llamar OTIF a una métrica de puntualidad solamente. Definir por separado:

- **Puntualidad:** pedidos entregados dentro de la ventana / pedidos que entran en el denominador acordado.
- **OTIF:** pedidos entregados completos y a tiempo / pedidos comprometidos incluidos en el denominador acordado.

Para comparaciones de aceptación se conservarán los valores de referencia de la especificación original cuando se use la planilla correspondiente. Se deberá dejar documentado si el fixture considera todas las entregas completas. No manipular la definición o el denominador para hacer coincidir un resultado esperado.

## 9. Pantallas y salidas

Pantallas principales:

1. Torre de control con mapa.
2. Línea de tiempo por vehículo.
3. Registro de eventos, propuesta y aprobación/rechazo de re-ruteo.
4. Hoja de ruta del conductor optimizada para celular, enlace a Google Maps, confirmar entrega y reportar novedad.
5. Tablero de capacidad, cambio de escenario y exportación a Excel.
6. Parámetros y maestros: CRUD, carga CSV e historial de cambios.
7. Indicadores diarios.
8. Patrones de ML.
9. Administración de tenants, solo superadministrador.

Salidas descargables: hoja de ruta en CSV/Excel y tablero de capacidad en un formato documentado. Asegurar exportación segura de fórmulas y manejo de nombres/acentos.

## 10. Criterios de aceptación del ejemplo

Los siguientes valores proceden de la planilla de referencia del prototipo original. **No deben presentarse como resultados reproducidos si esa planilla no está disponible y validada como fixture.** Sin la planilla, generar datos sintéticos y probar las fórmulas con casos pequeños calculados a mano. La ejecución debe indicar claramente cuál escenario aplica.

1. Balance actual: 48 vehículos requeridos frente a 42 propios: turbo 16, sencillo 11, tractomula 21.
2. Flota Lean: 35: turbo 11, sencillo 8, tractomula 16.
3. Monte Carlo P95: 47 ±1.
4. Mix óptimo: 43: 17 turbos, 5 doble troque y 21 tractomulas.
5. Propio vs. tercero: 37 propios: turbo 13, sencillo 8 y tractomula 16.
6. Proyección escenario base 2031 (CAGR 6 %): 67 vehículos.
7. Ruteo sin eventos (36 clientes, 4 turbos, salida a las 06:00): 36 entregas a tiempo; último regreso 15:55.
8. Plan fijo con cierre de la Calle 80 (08:15–12:30, factor ×2,5, radio 2,5 km): T-03 con 3 entregas tarde, 97 minutos de retraso y regreso 17:32 ±1 minuto.
9. Día completo, plan estático y cuatro eventos: referencia OTIF 84 % (31/37), 425 minutos de retraso y 1 pedido sin atender.
10. Día completo, ruteo dinámico y cuatro eventos: referencia OTIF 100 % (37/37), 0 minutos de retraso y reserva activada.
11. Un cliente con latitud 40 y ventana 14:00–10:00 debe rechazarse, con explicación para corregirlo.
12. Si falla el proveedor de tiempos de demostración, se usa `speed_profile` y se muestra el aviso correspondiente.

Las pruebas 11 y 12 deben pasar sin la planilla original. Las pruebas 1–10 se consideran reproducidas únicamente al cargar el archivo fuente correcto y verificar sus datos y fórmulas. En otros casos se informa “no verificadas contra la planilla de referencia”.

## 11. Arquitectura, stack y organización

### 11.1 Stack elegido

- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL 16 + PostGIS, Redis, OR-Tools, PuLP, NumPy, Pandas y scikit-learn.
- Frontend: React, TypeScript, Vite, Leaflet con OpenStreetMap y biblioteca ligera de gráficos (por ejemplo Recharts).
- Infraestructura: Docker Compose; proxy inverso con TLS de desarrollo.
- Calidad: pytest, pytest-cov, Ruff, mypy en modo estricto para dominio/aplicación, import-linter, Bandit, pip-audit, npm audit y pruebas de frontend con Vitest o Playwright.
- No usar claves de pago ni depender de proveedores pagados para que la demo básica funcione.

### 11.2 Backend: capas

Dentro de `APP/Backend` organizar el paquete de aplicación, por ejemplo:

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

Paquete Python: elegir un nombre genérico consistente e informar la elección. No utilizar el nombre de una empresa cliente como nombre del paquete.

### 11.3 Reglas de dependencia

- `domain` no importa `application`, `adapters`, FastAPI, SQLAlchemy, scikit-learn ni otros componentes de infraestructura. Solo se permiten librerías estándar estrictamente necesarias; cualquier excepción se justifica.
- `application` importa dominio y abstracciones de tipado. Define puertos y coordina casos de uso; no conoce implementaciones concretas.
- Los adaptadores pueden importar aplicación y dominio, pero nunca se importan entre sí. La comunicación se realiza mediante puertos.
- `bootstrap` es el único lugar que conoce las implementaciones concretas y las conecta mediante inyección de dependencias.
- Nada de singletons globales para estado por cliente ni imports de adaptadores dentro de casos de uso.
- ORM y esquemas HTTP no son entidades de dominio; existen mapeos explícitos.
- Datos GPS, tráfico y geocodificación entran solamente por puertos (`GpsPort`, `TrafficTimePort`, `GeocodingPort`).
- Las reglas se hacen cumplir con import-linter y pruebas arquitectónicas que fallen si se viola una dependencia.

### 11.4 SOLID demostrable

- **S — Responsabilidad única:** casos de uso por intención y clases de cálculo separadas, por ejemplo `DesignDemandCalculator`, `EffectiveCapacityCalculator`, `FleetRequirementCalculator`, `MonteCarloSimulator`, `FleetMixOptimizer` y `OwnVsThirdPartyAnalyzer`.
- **O — Abierto/cerrado:** estrategias separadas para métodos de capacidad, eventos y modelos de ML; se agregan implementaciones sin introducir condicionales crecientes en el caso de uso central.
- **L — Sustitución de Liskov:** adaptadores sustituibles bajo el mismo contrato; pruebas de contrato para implementaciones reales y simuladas.
- **I — Segregación de interfaces:** puertos pequeños, por ejemplo lector separado de escritor y flujo de posiciones separado de consulta puntual.
- **D — Inversión de dependencias:** dominio y aplicación dependen de abstracciones; implementaciones ensambladas en `bootstrap`.

`docs/ARQUITECTURA.md` incluirá un cuadro con el principio, archivos/clases que lo demuestran y pruebas relacionadas. No declarar un principio satisfecho solo por nombrarlo.

## 12. Multi-tenancy: base de datos por empresa

### 12.1 Topología para la demo

Para eliminar la ambigüedad entre la base de control y las bases de clientes, la demo levantará **tres instancias/servicios PostgreSQL** en Docker Compose:

- `pg-control`: registro central de tenants.
- `pg-tenant-a`: base de datos de Empresa Demo A.
- `pg-tenant-b`: base de datos de Empresa Demo B.

Cada base de tenant puede migrarse y, en producción, ubicarse en un servidor distinto. Tres contenedores de base de datos permiten demostrar separación lógica y de instancia en el entorno local; no equivalen a aislamiento entre máquinas físicas. Redis, backend, frontend y proxy serán servicios separados según convenga a Docker Compose.

### 12.2 Registro central y conexión por tenant

La base de control guarda `tenant_id`, nombre, slug, estado (activo/suspendido), configuración de conexión cifrada, versión de esquema, plan y fechas. Las credenciales de conexión jamás se escriben en logs ni en el repositorio. El cifrado usa un secreto externo a Git, configuración validada al inicio y un puerto `SecretsPort`.

- El tenant se obtiene del claim firmado del token autenticado, no de un parámetro que el cliente pueda manipular.
- `TenantConnectionPort` devuelve una sesión ligada a la base del tenant autenticado. Los repositorios no reciben un `tenant_id` arbitrario de cada consulta.
- El pool de conexiones se administra por tenant, con límites, cierre ordenado y protección para evitar agotamiento de recursos.
- Todas las consultas y trabajos asíncronos deben conservar explícitamente el contexto de tenant; prohibido usar variables globales mutables para el tenant actual.
- Dos análisis o simulaciones concurrentes de tenants distintos no deben compartir datos, modelos, archivos, cachés ni resultados por accidente.

### 12.3 Migraciones y aprovisionamiento

Alembic tendrá dos líneas de migración: `control_plane` y `tenant`. Debe existir un comando para migrar un tenant individual y para procesarlos todos, con reporte por tenant. `ProvisionTenant` crea la base, aplica esquema, parámetros iniciales, usuario administrador y registro de control con manejo de errores compensatorios/idempotencia documentada.

Modelos y artefactos de ML se entrenan por tenant y se almacenan en ubicación separada; nunca se combinan datos de empresas distintas.

### 12.4 Pruebas obligatorias de aislamiento

1. Un usuario de Empresa Demo A no puede leer ni modificar objetos de Empresa Demo B, incluso alterando IDs, cabeceras o cuerpo.
2. Un token de A usado contra recursos de B produce 403/404 sin filtrar datos del tenant ajeno.
3. Ejecuciones simultáneas de los módulos 1 y 2 no mezclan resultados ni estados.
4. Suspender un tenant bloquea sus accesos conforme a una política explícita.
5. Caché, artefactos ML, exportaciones, websockets y tareas programadas respetan el tenant.

`docs/MULTITENANT.md` documentará arquitectura, alta, traslado a otro servidor, respaldo/restauración por tenant y límites conocidos.

## 13. Machine learning

Los modelos se implementan detrás de los puertos `DemandForecaster`, `AnomalyDetector`, `DelayRiskPredictor` y `PatternMiner`, con adaptadores scikit-learn. El dominio conoce tipos propios (`Forecast`, `Anomaly`, `DelayRisk`, `Segment`), no objetos de scikit-learn. Entrenamiento y predicción son casos de uso (`TrainModels`, `DetectPatterns`). Los resultados deben tener lenguaje claro, límites conocidos y procedencia visible.

Metadatos versionados por tenant: nombre, versión, fecha, métricas, hash del artefacto y descripción del conjunto de entrenamiento. Verificar el hash antes de cargar. No cargar serializaciones no confiables ni artefactos cuyo hash no coincida con el registro.

### 13.1 Pronóstico diario por ruta

- Variables: día de semana, mes, festivos de Colombia, rezagos 7/14 días y promedio móvil.
- Modelo: gradient boosting; regresión por cuantiles para obtener P50/P90 cuando la implementación y los datos lo permitan.
- Comparar contra línea base ingenua estacional con MAE y MAPE; manejar explícitamente denominadores cero/valores ausentes para MAPE.
- Interfaz: mostrar pronóstico, intervalo, línea base y comparación contra percentil histórico.

### 13.2 Detección de anomalías

Isolation Forest para tiempos de servicio y espera por cliente, muelle y hora. Ordenar por severidad y explicar con frases legibles, por ejemplo: “Este cliente tuvo esperas mayores a dos veces su patrón habitual los viernes entre las 10:00 y las 12:00”. Distinguir evidencia estadística de causalidad.

### 13.3 Riesgo de retraso

Clasificador como HistGradientBoosting con probabilidad de quedar fuera de ventana según hora, cliente, carga, factor de tráfico y paradas restantes. Se usa para priorizar alertas y proponer re-secuenciación. Reportar precisión, recall, AUC y Brier/calibración. No mostrar probabilidad como certeza.

### 13.4 Segmentación

KMeans o DBSCAN sobre tiempo de servicio, tamaño de pedido, amplitud de ventana y estacionalidad. Dar a los segmentos nombres comprensibles, explicar sus características y evitar sugerir que son categorías objetivas universales.

### 13.5 Datos y pruebas de ML

Generador determinista con semilla fija, 60–90 días de historia, alrededor de 15 corredores/rutas y entre 40–300 clientes por tenant-demo. Sembrar patrones conocidos: picos los lunes, un cliente con esperas largas los viernes, efecto de tráfico en horas pico y estacionalidad quincenal. La interfaz e informes dirán que son patrones en datos sintéticos.

Las pruebas `tests/ml` deben verificar con semilla fija que el modelo de demanda supera la línea base en el fixture definido, que el detector encuentra el patrón sembrado, que el clasificador supera a una predicción ingenua en una partición reproducible y que los modelos no usan datos de otros tenants. Usar división temporal de entrenamiento/prueba para evitar fuga de información; documentar tolerancias y evitar umbrales arbitrarios que no representen el fixture.

Programar reentrenamiento y permitir dispararlo manualmente por tenant. Mostrar variables influyentes por importancia de permutación cuando sea aplicable, fecha de entrenamiento y métricas.

## 14. Seguridad y privacidad

Entregables: `docs/SEGURIDAD_OWASP.md`, `docs/MODELO_AMENAZAS.md` (STRIDE para login, carga CSV, eventos, GPS y aprovisionamiento) y `docs/PRIVACIDAD.md`. Para cada categoría se indica riesgo concreto, control, archivo/línea o componente, prueba asociada y estado: implementado en demo, parcial o pendiente. El informe solo puede marcar un control implementado si existe evidencia verificable.

Controles requeridos alineados con OWASP Top 10 2021:

- **A01 Control de acceso roto:** RBAC para gerencia, despachador, conductor, administrador y superadministrador; denegar por defecto; comprobar permisos y pertenencia al objeto. Un conductor solo ve su hoja de ruta; un despachador no edita parámetros exclusivos de gerencia. Incluir pruebas multi-tenant y protección contra enumeración de IDs.
- **A02 Fallas criptográficas:** Argon2id para contraseñas; TLS en proxy de desarrollo; cifrado autenticado de secretos de conexión gestionado por `SecretsPort`; secretos por variables/servicio seguro y nunca en código; logs sin información sensible. Cifrado en reposo de ubicaciones y otros datos personales se implementará o figurará expresamente como pendiente.
- **A03 Inyección:** ORM/consultas parametrizadas; no construir SQL mediante concatenación; validación Pydantic estricta; CSV/Excel validado por esquema, tamaño y contenido; neutralizar fórmulas de hojas de cálculo; no usar `dangerouslySetInnerHTML` para datos de usuario.
- **A04 Diseño inseguro:** validaciones de dominio; límites de tasa por usuario y tenant; confirmación humana para cambios de alto impacto; modelo de amenazas; límites de recursos y tiempos del solver.
- **A05 Configuración incorrecta:** CSP, HSTS donde corresponda, `X-Content-Type-Options`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`; CORS con lista blanca explícita; debug apagado fuera de desarrollo; documentación API deshabilitada o protegida en entornos no locales; contenedores no-root; imágenes mínimas; bases sin exposición externa innecesaria; configuración validada al arrancar y fallo seguro si falta un secreto obligatorio.
- **A06 Componentes vulnerables:** dependencias fijadas y lockfiles; `pip-audit`, `npm audit` y SBOM; política de actualización documentada.
- **A07 Identificación/autenticación:** JWT de vida corta, refresh token rotatorio y revocable si se implementa en demo; bloqueo/retardo progresivo, política de contraseñas, errores de login genéricos, cierre de sesión con revocación y claim de tenant firmado. MFA TOTP pendiente para producto completo si no se construye en demo.
- **A08 Integridad de software/datos:** lockfiles, verificación de artefactos ML por hash, no deserializar archivos no confiables, migraciones versionadas/revisadas, validación de cargas y auditoría de parámetros con valor anterior/vigencia.
- **A09 Registro/monitoreo:** auditoría estructurada (quién, qué, cuándo, tenant, resultado, correlación) para login, cambios maestros/parámetros, eventos, aprobaciones y aprovisionamiento; sin secretos ni datos personales innecesarios; alertas sobre fallos de autenticación/accesos denegados; health endpoint sin información sensible.
- **A10 SSRF:** destinos salientes limitados a hosts permitidos configurados; ninguna URL arbitraria desde el usuario; bloquear loopback, redes privadas y endpoints de metadatos en clientes HTTP salientes cuando corresponda; timeouts y reintentos limitados.

Privacidad: `docs/PRIVACIDAD.md` será un borrador técnico que describa finalidad, minimización, retención, acceso, auditoría y borrado de la ubicación de vehículos/conductores. No asumir automáticamente una clasificación legal única para toda ubicación GPS; dejar la clasificación y obligaciones aplicables para revisión jurídica a la luz del contexto de tratamiento y las normas de Colombia.

Ejecutar `bandit`, `pip-audit` y `npm audit`, además del escaneo de secretos elegido. Si un comando no está instalado, no hay conexión, no se puede ejecutar o devuelve error, informar exactamente ese resultado y no decir “sin vulnerabilidades” por ausencia de escaneo.

## 15. Datos de demo, simulación y tiempo real

- Dataset sintético reproducible con semilla, ambientado en Bogotá/Funza y CEDI en Funza.
- Empresa Demo A: alrededor de 48 vehículos entre turbos, sencillos, doble troque y tractomulas; alrededor de 36 clientes de distribución urbana y cuatro turbos para el caso de ruteo de referencia.
- Empresa Demo B: dataset diferente y tamaño distinto para demostrar separación total.
- Simulador GPS detrás de `GpsPort`, marcado `DEMO-ONLY`; mueve vehículos por sus rutas con reloj acelerado configurable (por ejemplo, un minuto real equivale a 30 minutos simulados), emite posiciones cada 1–5 minutos simulados, detecta llegada por geocerca y permite pausar, acelerar y reiniciar.
- Reloj real y simulado detrás de `ClockPort`.
- WebSocket o Server-Sent Events para actualizaciones y alertas hacia el navegador; asegurar autenticación y contexto de tenant en la conexión y en cada evento.
- Botón “Inyectar evento” para el despachador; los eventos disparan `HandleEvent` y muestran la propuesta de aprobación/rechazo.
- Enlace a Google Maps con URL oficial `maps/dir/?api=1&...`, respetando el máximo de paradas intermedias aplicable; el vínculo de navegación no debe exponerse como integración API.
- Sembrar usuarios por rol y tenant. Generar contraseñas aleatorias solo en el proceso de seed y mostrarlas una sola vez en consola; no guardarlas en el repositorio, documentación compartida ni logs persistentes.

## 16. Entregables

### Código e infraestructura

- Backend bajo `APP/Backend`, frontend bajo `APP/Frontend`.
- Docker Compose para proxy TLS de desarrollo, frontend, backend, Redis, `pg-control`, `pg-tenant-a` y `pg-tenant-b`.
- Scripts/CLI de siembra, aprovisionamiento y entrenamiento.
- Makefile/task runner con comandos equivalentes a `make up`, `make seed`, `make test`, `make lint`, `make security` y `make demo`.
- `.env.example` sin secretos reales y `.gitignore` correcto.
- La secuencia de demo debe dejar la aplicación lista desde un estado limpio; instrucciones de arranque y limitaciones deben figurar en el README.

### Documentación en `docs/`

- `ARQUITECTURA.md`: diagrama de capas/puertos/adaptadores y matriz SOLID-evidencia.
- `MULTITENANT.md`: topología, aprovisionamiento, migración, traslado, respaldo y límites.
- `ML.md`: modelos, datos, métricas, reproducibilidad, límites y aislamiento.
- `SEGURIDAD_OWASP.md`: informe por categoría y resultados reales.
- `MODELO_AMENAZAS.md`: STRIDE y riesgos residuales.
- `PRIVACIDAD.md`: borrador de privacidad y retención.
- `DEMO_GUION.md`: pasos para el demo.
- `GLOSARIO.md`: español-inglés, por ejemplo cliente=customer, vehículo=vehicle, pedido=order, ruta=route, parada=stop, ventana horaria=time window, flota=fleet, corredor=corridor y CEDI=distribution center.
- `DECISIONES.md`: decisiones arquitectónicas o de negocio en formato ADR corto (contexto, decisión, consecuencias).
- `DEUDA_DEMO.md`: elementos `DEMO-ONLY`, puertos que reemplazar y pasos para sustituirlos.
- `ROADMAP.md`: transición del demo al producto completo.
- `ESTADO_IMPLEMENTACION.md`: progreso por fase, pruebas y pendientes.

### Orden requerido para el roadmap

1. Adaptadores reales para GPS y proveedores de rutas/geocodificación/optimización.
2. Integración con ERP/TMS/CRM por API.
3. Endurecimiento de seguridad: MFA, pruebas de penetración externas, rotación de secretos y cifrado en reposo.
4. Operación multi-tenant a escala: aprovisionamiento automatizado, respaldos, observabilidad por tenant y límites por plan.
5. Facturación por suscripción y licenciamiento por vehículo.
6. Mejora de modelos de ML con datos reales y evaluación operacional.

## 17. Calidad y definición de terminado

- Cobertura de pruebas del dominio >= 90 %, con cobertura informada y no manipulada.
- Pruebas unitarias de casos de uso con dobles de puertos.
- Pruebas de integración contra PostgreSQL real en entorno reproducible.
- Pruebas de contrato por puerto/adaptador.
- Pruebas de arquitectura que detecten dependencias prohibidas.
- Pruebas de seguridad que cubran los diez riesgos OWASP priorizados en esta especificación.
- Pruebas de ML con semilla fija y partición sin fuga de datos.
- Pruebas frontend y al menos un flujo e2e que recorra el guion del demo.
- Ruff y mypy (strict para domain/application) sin errores; import-linter sin violaciones.
- Bandit, pip-audit, npm audit y escaneo de secretos ejecutados y reportados; un hallazgo no se oculta. Los estados parciales deben quedar expresos.
- `make up`, `make seed` y `make demo` deben permitir reproducir el demo siguiendo las instrucciones en una máquina limpia con Docker disponible; si una limitación del entorno impide validarlo, no declarar el criterio aprobado.
- Nunca hay secretos en el repositorio.
- Los casos 11 y 12 de aceptación pasan sin planilla. Los casos 1–10 solo se declaran reproducidos si se verifican contra el fixture fuente correcto.
- El informe final distingue: implementado, probado, parcial, pendiente y demo-only.

### Cómo ejecutar controles por fase

Después de cada incremento, ejecutar las pruebas unitarias y de contrato relacionadas con el cambio, además de los chequeos arquitectónicos o de seguridad que correspondan. En cada hito integrar y ejecutar los controles globales relevantes. Al finalizar, correr el conjunto completo. No es necesario repetir auditorías costosas sin cambios relacionados en cada microincremento, pero sí registrar la última ejecución y volver a ejecutarlas en hitos y al cierre.

## 18. Orden de construcción sugerido

1. Diagnóstico del workspace, inspección de especificación/planilla, riesgos y plan aprobado. No programar antes de la aprobación.
2. Esqueleto del repositorio, capas y reglas de arquitectura; import-linter, pruebas de arquitectura, CI local y Docker Compose con `pg-control`, `pg-tenant-a`, `pg-tenant-b` y Redis.
3. Dominio y casos de uso de capacidad P1–P9 con pruebas unitarias y cálculos manuales.
4. Multi-tenancy: registro central, gestor de conexiones, migraciones por tenant, `ProvisionTenant` y pruebas de aislamiento.
5. Persistencia, autenticación, RBAC, auditoría y controles OWASP base con pruebas.
6. Cargas CSV, maestros, parámetros e historial.
7. Dominio y casos de uso de ruteo: cálculo base, plan de mañana, eventos y versionado.
8. Generador sintético, cuatro casos de ML y pantalla de patrones.
9. Simulador GPS, tiempo real, torre de control, línea de tiempo, hoja de ruta del conductor e indicadores.
10. Informe OWASP, documentación restante, guion del demo, ensayo del flujo completo y reporte final.

Cada fase tiene que producir software ejecutable y pruebas proporcionadas al alcance. Las dependencias que impidan pasar a la siguiente fase se reportan como bloqueo, no se ocultan.

## 19. Puerta de entrada obligatoria: diagnóstico y aprobación

Antes de escribir código, el agente debe:

1. Confirmar si puede leer esta especificación y `CLAUDE.md`.
2. Inspeccionar el workspace sin sobrescribir archivos existentes y localizar la planilla funcional original, si existe.
3. Informar qué herramientas/servicios están disponibles y cuáles no pudo comprobar.
4. Identificar contradicciones o decisiones de negocio que realmente bloqueen la arquitectura o el resultado.
5. Presentar un plan corto con estructura, fases, criterios de aceptación y riesgos.

Debe detenerse después de presentar el plan y esperar aprobación explícita antes de modificar archivos, instalar dependencias, ejecutar migraciones o programar. Las preguntas se limitan a decisiones indispensables; las decisiones menores se documentan con justificación en `docs/DECISIONES.md`.
