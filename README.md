# Demo: planeación de flota y ruteo dinámico

**DATOS DE DEMOSTRACIÓN.** Todo el contenido numérico es sintético. Especificación completa en
[`DOCS.MD`](DOCS.MD); bitácora de lo hecho en [`docs/REGISTRO_DEMO.md`](docs/REGISTRO_DEMO.md);
estado en [`docs/ESTADO_IMPLEMENTACION.md`](docs/ESTADO_IMPLEMENTACION.md).

## Estado actual
- **Backend:** capacidad de flota (P1–P9), ruteo dinámico (plan de la mañana con OR-Tools y heurística,
  eventos, propuestas con aprobación, versiones del plan, indicadores), multi-tenancy en memoria,
  autenticación, roles, auditoría y API HTTP. **Frontend:** inicio de sesión, capacidad, torre de
  control con mapa, línea de tiempo, eventos y re-ruteo, indicadores diarios, empresas y auditoría.
  GPS simulado (geocerca, "sin señal"), tiempo real por SSE, hoja de ruta del conductor y maestros y
  parámetros (CRUD, carga CSV con previsualización, parámetros con vigencia, historial, Excel en el
  servidor), y ML sobre datos **sintéticos** (pronóstico de demanda, anomalías, riesgo de retraso y
  segmentos) con la pantalla "Patrones detectados".
- **No hay base de datos:** la persistencia es en memoria (DEMO-ONLY) y PostgreSQL está comentado a
  propósito (`infra/docker-compose.yml`). Al reiniciar el backend se pierde el estado.

## Puesta en marcha (Windows, PowerShell)

Requisitos: Python ≥ 3.12 (probado en 3.12 y 3.13). No se necesita Docker ni servicios de pago.

> Si `pip` falla con `CERTIFICATE_VERIFY_FAILED` (proxy o antivirus que intercepta HTTPS), no
> desactive la verificación: instale `truststore` y use `pip install --use-feature=truststore ...`.
> El paquete local se instala con `pip install -e . --no-deps --no-build-isolation` (requiere
> `editables`, ver `docs/REGISTRO_DEMO.md`, sesión 3).

```powershell
# 1) Backend (una vez), desde APP/Backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps

# 2) Frontend (una vez), desde la raíz: instala Node local verificado y las dependencias
powershell -ExecutionPolicy Bypass -File scripts\setup-frontend.ps1

# 3) Arrancar la demo (abre dos ventanas y el navegador)
powershell -ExecutionPolicy Bypass -File scripts\start-demo.ps1
```

En la ventana **Backend** aparece una tabla con los usuarios sembrados y sus **contraseñas
aleatorias, que se muestran una sola vez**. Anótelas: no se guardan en ningún sitio y cambian en
cada arranque.

| Empresa | Usuario | Rol | Qué verá |
|---|---|---|---|
| Empresa Demo A / B | `gerencia` | Gerencia | Tablero de capacidad, indicadores diarios y patrones detectados (puede reentrenar) |
| Empresa Demo A / B | `admin` | Administrador de la empresa | Tablero, auditoría y *Maestros y parámetros* de su empresa |
| Empresa Demo A / B | `despachador` | Despachador | Torre de control, línea de tiempo, eventos y re-ruteo, indicadores, patrones detectados |
| Empresa Demo A / B | `conductor` | Conductor | Mi hoja de ruta (vehículo T-01) |
| (sin empresa) | `superadmin` | Superadministrador | Administración de empresas y auditoría global |

Recorrido del despachador (≈5 min): entrar como `despachador` de la Empresa A → *Torre de control* →
**Reanudar** el reloj (o *+1 h*) → *Eventos y re-ruteo* → inyectar un **cierre vial** (el formulario
trae la Calle 80), un **pedido urgente**, un **cambio de ventana** y una **avería** → leer el impacto de
cada propuesta y **aprobar o rechazar** → comparar versiones → *Indicadores diarios*. Con **Simular
falla del proveedor de tiempos** aparece el aviso "Tiempos estimados sin tráfico". El reloj se pausa solo
cuando hay una propuesta por decidir. *Reiniciar día* vuelve al plan de las 05:00. En la tabla de
vehículos, **Cortar señal** simula un GPS caído: a los 15 min simulados aparece la alerta "sin señal"
y el plan se conserva. Como `conductor` (Empresa A): *Mi hoja de ruta* → abrir en Google Maps,
confirmar una entrega o reportar una novedad (el despachador la ve en la torre de control).

Recorrido del administrador (≈3 min): entrar como `admin` → *Maestros y parámetros* → en *Clientes*, **Nuevo**
(pruebe una latitud 40 o una ventana 14:00–10:00: se rechaza con la explicación) → **Cargar CSV**, pegar o
subir un archivo y revisar la previsualización (nada se guarda hasta **Aplicar carga**; con errores no se
puede aplicar) → *Parámetros* → **Cambiar** la reserva con una vigencia futura y un motivo → *Historial*
para ver quién cambió qué y el valor anterior → **Exportar Excel**. Los cambios se leen al recalcular el
tablero de capacidad y al **reiniciar el día** operativo del ruteo.

Recorrido de patrones (≈2 min): entrar como `gerencia` → *Patrones detectados* (la primera vez entrena los
modelos y tarda unos segundos) → elegir un corredor y ver el pronóstico con su intervalo → leer la anomalía
principal (un cliente con esperas largas los viernes entre las 10:00 y las 12:00: es un patrón sembrado en
los datos sintéticos) → revisar el riesgo de retraso, los segmentos y la procedencia de cada modelo →
**Reentrenar modelos** (crea la versión 2). En *Capacidad de flota* aparece el pronóstico ML frente al
percentil histórico.

Sugerencia de recorrido: entrar como `gerencia` de la Empresa A, ver el tablero y exportar el CSV;
cerrar sesión y entrar a la Empresa B para comprobar que sus datos son distintos; entrar como
`superadmin`, crear una empresa, suspender la B y verificar que sus usuarios ya no pueden entrar.

## Mostrar la demo a otras personas

Guía completa, usuarios y riesgos: [`docs/HOSPEDAJE_DEMO.md`](docs/HOSPEDAJE_DEMO.md). Resumen:

- **Desde su PC con un túnel HTTPS:** `powershell -ExecutionPolicy Bypass -File scripts\share-demo.ps1`
  (pide las contraseñas, compila la interfaz y arranca todo en un solo puerto) y abra el túnel hacia
  `http://127.0.0.1:8000`.
- **En un servidor (p. ej. Railway):** el `Dockerfile` de la raíz construye todo; defina `JWT_SIGNING_KEY`,
  `DEMO_PASSWORD` y `DEMO_SUPERADMIN_PASSWORD` como variables del servicio (ver `.env.example`).
  La imagen **no se ha construido** en este PC.

## Comandos de calidad

Backend (desde `APP/Backend`):

```powershell
.\.venv\Scripts\python.exe -m pytest --cov                      # pruebas + cobertura del dominio
.\.venv\Scripts\python.exe -m ruff check src tests              # lint
.\.venv\Scripts\python.exe -m mypy                              # tipos (strict en domain/application)
.\.venv\Scripts\python.exe -c "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())"
.\.venv\Scripts\python.exe -m bandit -r src                     # seguridad estática
.\.venv\Scripts\python.exe -m pip_audit                         # dependencias
.\.venv\Scripts\python.exe -m fleetplanner.bootstrap capacity   # informe de capacidad en consola
.\.venv\Scripts\python.exe -m fleetplanner.bootstrap serve      # solo la API (puerto 8000)
```

Frontend (desde `APP/Frontend`, con Node local: `$env:Path = "$env:LOCALAPPDATA\fleetplanner-tools\node;$env:Path"`):

```powershell
npm run typecheck   # tsc estricto
npm test            # vitest
npm run build       # build de producción
npm audit
```

El `Makefile` de la raíz no se ha probado (no hay `make`); los comandos anteriores sí se ejecutaron.
`make up` y `make seed` no existen aún (requieren PostgreSQL).

## Estructura
`APP/Backend` (API, dominio, casos de uso, adaptadores, pruebas) · `APP/Frontend` (React + Vite + Leaflet) ·
`infra/` (Compose con PostgreSQL comentado) · `scripts/` · `docs/`.

## Notas
- `APP/Frontend/node_modules` es una unión hacia `%LOCALAPPDATA%\fleetplanner-tools` para que OneDrive
  no sincronice miles de archivos (D-015).
- Mensajes de la interfaz y de la API en español; identificadores de código en inglés.
