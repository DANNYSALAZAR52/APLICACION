# Especificaciones técnicas de frontend

Este documento complementa `DOCS.MD`. El frontend facilita la demostración de los flujos de negocio, pero nunca sustituye reglas, autorización ni validaciones del backend.

## 1. Ubicación y stack

Todo el frontend vive en `APP/Frontend/`. Stack previsto: React, TypeScript y Vite. Mapa con Leaflet/OpenStreetMap y gráficos con una biblioteca ligera como Recharts. Pruebas con Vitest y Testing Library o Playwright; el plan decidirá la combinación según el workspace.

Estructura sugerida:

```text
APP/Frontend/
├── src/
│   ├── app/                 # composición, rutas, proveedores y configuración
│   ├── api/                 # cliente HTTP, contratos y gestión de errores
│   ├── domain-ui/           # tipos, formatos y reglas exclusivamente de presentación
│   ├── features/
│   │   ├── auth/
│   │   ├── capacity/
│   │   ├── control-tower/
│   │   ├── vehicle-timeline/
│   │   ├── events/
│   │   ├── driver-route/
│   │   ├── daily-indicators/
│   │   ├── patterns/
│   │   ├── master-data/
│   │   └── tenant-admin/
│   ├── components/          # componentes compartidos sin lógica de negocio ajena
│   ├── hooks/
│   ├── styles/
│   └── test/
├── public/
├── package.json
├── lockfile
├── tsconfig.json
└── vite.config.ts
```

Se permite ajustar nombres internos manteniendo separación clara de funcionalidades y contratos. Evitar una carpeta única con componentes gigantes o toda la lógica dentro de una pantalla.

## 2. Principios de interfaz

- Interfaz, validaciones visibles, textos de ayuda, errores, fechas y formatos en español.
- Diseño profesional, legible y responsive: escritorio para gerencia/despacho y celular para conductor.
- Mostrar una etiqueta persistente **DATOS DE DEMOSTRACIÓN** en vistas con dataset sintético o GPS simulado.
- No presentar el mapa simulado como posición GPS real ni los tiempos de respaldo como tráfico en vivo.
- Mantener consistencia de colores, tipografía, estados, espaciado, iconografía y componentes de formularios.
- No usar color como único indicador de estado. Acompañar alertas con texto o icono accesible.
- Formularios con etiquetas, errores vinculados a los campos, foco visible, contraste adecuado y navegación por teclado.
- Evitar animaciones excesivas; el reloj acelerado debe poder pausarse y su velocidad mostrarse claramente.
- No sobrecargar la torre de control con paneles que oculten el mapa o las alertas prioritarias.

## 3. Organización y límites

- `api/` encapsula llamadas HTTP, tipado, manejo de errores, reintentos justificados y eventos en tiempo real. Los componentes no construyen URLs de API dispersas.
- `domain-ui/` contiene tipos de presentación, formatos de unidades, fechas, moneda y conversiones visuales. No debe convertirse en una segunda implementación de las reglas de negocio del backend.
- `features/` mantiene pantallas, componentes y hooks específicos de cada módulo.
- `components/` solo contiene elementos compartidos cuando existe una necesidad real; evitar abstracciones genéricas prematuras.
- El estado del usuario autenticado y el tenant activo se derivan de una sesión confiable del backend. No permitir que cambiar un identificador en la UI habilite acceso a otro tenant.
- Estado de carga, vacío, error, permisos insuficientes, datos obsoletos y desconexión se diseñan explícitamente.

## 4. Mapa, tiempo real y rendimiento

- Usar Leaflet y tiles de OpenStreetMap; documentar atribución y límites de uso de los tiles.
- Separar marcador, trayecto, parada, CEDI, evento vial y alertas mediante leyendas y accesibilidad.
- Para GPS simulado, mostrar estado de simulación, hora simulada, velocidad de reloj y última actualización. Botones para pausar, reiniciar y acelerar solo aparecen donde el rol lo permite.
- WebSocket/SSE debe gestionar conexión, reconexión, desconexión, mensajes inválidos y caducidad de sesión. El servidor decide el tenant autorizado.
- Evitar renderizar de nuevo el mapa completo por cada posición. Actualizar capas/marcadores de forma localizada y limitar grandes conjuntos de puntos.
- Si no hay posición reciente, mostrar “Sin señal” con la hora de la última posición; no seguir moviendo el marcador como si la señal existiera.
- Cuando el proveedor de tráfico falle, presentar aviso “Tiempos estimados sin tráfico”.

## 5. Pantallas requeridas

### 5.1 Torre de control

Mapa con CEDI, vehículos, recorridos, paradas y eventos. Leyenda, filtros por estado/vehículo y panel de entregas en riesgo. Mostrar número de versión del plan y estado de conexión. Seleccionar un vehículo abre detalle sin ocultar todas las referencias de contexto.

### 5.2 Línea de tiempo por vehículo

Mostrar cada vehículo con su secuencia de paradas, hora estimada, inicio/fin de servicio, retraso y estado. Diferenciar orden planificada y ejecución real/simulada. Cuando hay un cambio, presentar qué se modificó, por qué y en qué versión.

### 5.3 Registro de eventos y re-ruteo

Permitir registrar cierre vial (zona/radio/factor/horario), pedido urgente, cambio de ventana y avería. Antes de confirmar, mostrar propuesta, efecto en paradas, retraso, distancia/costo cuando estén disponibles y si activa reserva/tercero. El despachador puede aprobar o rechazar con confirmación cuando afecta varios vehículos o recursos externos. Nunca aplicar la propuesta solo por abrirla.

### 5.4 Hoja de ruta del conductor

Vista mobile-first, con lista ordenada de entregas, dirección, ventana, carga o pedido relevante, estado y acciones grandes y claras para confirmar entrega o reportar novedad. Incluir enlace a Google Maps construido por el backend o por un helper probado con URL oficial y número máximo de paradas respetado. No exponer datos de otras rutas/conductores.

### 5.5 Tablero de capacidad

Tarjetas/gráficos por método, flota actual/requerida, brecha por tipo, cinco años y tres escenarios. Mostrar filtros, fecha de cálculo, parámetros relevantes, cantidad/calidad de datos y opción de recálculo. Incluir comparación ML vs. percentil histórico y rango de pronóstico. Exportar en Excel/CSV con manejo seguro de fórmulas.

### 5.6 Maestros y parámetros

CRUD de vehículos, tipos, clientes, rutas, compatibilidad, perfiles de velocidad, escenarios y parámetros. Mostrar historial de cambios y vigencia. Importación CSV con previsualización de filas válidas/errores, resumen y confirmación antes de aplicar. No permitir al frontend saltarse validaciones del backend.

### 5.7 Indicadores diarios

Mostrar puntualidad, OTIF conforme a la definición configurada, retrasos, kilómetros, utilización y costos cuando existan datos suficientes. Comparar plan estático y dinámico con los mismos pedidos, condiciones y denominadores. Exponer supuestos y distinguir valores de referencia sintéticos de métricas operacionales reales.

### 5.8 Patrones ML

Panel con pronóstico de demanda, anomalías de espera/servicio, segmentos y riesgo de retraso. Cada hallazgo debe mostrar descripción, severidad o probabilidad cuando corresponda, ventana temporal, cantidad de observaciones, fecha/version del modelo y aviso de datos sintéticos. Evitar presentar correlaciones como causas.

### 5.9 Administración de tenants

Solo visible para superadministrador. Listar slug, nombre genérico, estado y metadatos que no expongan secretos. Flujos de alta, suspensión/reactivación y estado de migración con confirmación y resultado. No mostrar cadenas de conexión, contraseñas ni secretos. Restringir cada acción tanto en frontend como en backend.

## 6. Roles y navegación

- Gerencia: tablero de capacidad, proyecciones, patrones permitidos e indicadores.
- Despachador: torre de control, línea de tiempo, eventos, propuestas y métricas operacionales.
- Conductor: solo su hoja de ruta, confirmación y novedades.
- Administrador de tenant: maestros, cargas, parámetros permitidos y usuarios según política definida.
- Superadministrador: administración de tenants y funciones técnicas globales estrictamente necesarias.

La UI oculta acciones no autorizadas para facilitar la experiencia, pero esto no se considera control de seguridad. El backend aplica RBAC y permisos por objeto.

## 7. API, datos y errores

- Definir tipos TypeScript para las respuestas de API y evitar `any` en contratos esenciales.
- No duplicar los algoritmos de capacidad o ruteo del backend en JavaScript.
- Normalizar errores en un componente o hook reutilizable: mensaje claro en español, código de seguimiento cuando exista y sin stack trace.
- No incluir tokens, secretos ni datos personales en logs del navegador.
- Cancelar consultas obsoletas cuando cambian filtros o pantallas. Mostrar cuándo un dato no está actualizado.
- Formatear fechas con zona horaria explícita de Bogotá en vistas operativas; no interpretar silenciosamente fechas sin zona.
- Diferenciar ausencia de datos de cero y estados “no calculado”, “sin datos suficientes”, “error” y “resultado disponible”.
- Evitar almacenar credenciales en localStorage; seguir la estrategia de sesión definida por el backend y documentar amenazas y mitigaciones.

## 8. Accesibilidad, seguridad y privacidad

- Controles accesibles por teclado, etiquetas en formularios, foco, contraste y textos alternativos pertinentes.
- No insertar HTML no confiable ni datos externos mediante `dangerouslySetInnerHTML`.
- No renderizar mensajes del backend como HTML sin sanitización.
- Tratar coordenadas, información de vehículos y datos de clientes como datos que requieren minimización y acceso autorizado.
- Evitar exponer información sensible en URL, telemetría o mensajes de error.
- Hacer que la pantalla de sesión vencida, permisos denegados y desconexión tenga un camino claro para recuperar o cerrar sesión.

## 9. Pruebas de frontend

Pruebas unitarias/componentes para:

- Estados de carga, error, vacío y éxito.
- Formatos y validaciones visibles.
- Renderizado condicionado por roles sin tomarlo como control de seguridad.
- Etiqueta “DATOS DE DEMOSTRACIÓN”.
- Formularios de eventos y confirmación/rechazo.
- Errores del API y desconexión/reconexión de tiempo real.
- Validación de contenido del tablero, unidades y estados de datos ausentes.
- Vistas responsive y hoja de ruta mobile-first.

E2E mínimo del guion: inicio de sesión, tablero de capacidad, patrones, torre de control, inyección/aprobación de evento, nueva versión del plan, hoja de ruta y comparación de indicadores; además, verificar que el rol superadministrador es el único que ve administración de tenants.

## 10. Criterio de terminado

Una pantalla está terminada si usa contratos reales del backend o fixtures claramente identificados, contiene estados de carga/vacío/error, respeta permisos y accesibilidad básica, tiene pruebas pertinentes y funciona en el tamaño objetivo. No presentar botones decorativos que no ejecuten una acción: toda acción visible debe funcionar o aparecer explícitamente deshabilitada con explicación.
