# Demo: planeación de flota y ruteo dinámico

**DATOS DE DEMOSTRACIÓN.** Todo el contenido numérico es sintético. Especificación completa en
[`DOCS.MD`](DOCS.MD); bitácora de lo hecho en [`docs/REGISTRO_DEMO.md`](docs/REGISTRO_DEMO.md);
estado en [`docs/ESTADO_IMPLEMENTACION.md`](docs/ESTADO_IMPLEMENTACION.md).

## Estado actual
- **Backend:** capacidad de flota (P1–P9), multi-tenancy en memoria, autenticación, roles, auditoría
  y API HTTP. **Frontend:** inicio de sesión, tablero de capacidad, administración de empresas y
  auditoría. Ruteo, ML, GPS y el resto de pantallas están pendientes.
- **No hay base de datos:** la persistencia es en memoria (DEMO-ONLY) y PostgreSQL está comentado a
  propósito (`infra/docker-compose.yml`). Al reiniciar el backend se pierde el estado.

## Puesta en marcha (Windows, PowerShell)

Requisitos: Python ≥ 3.12 (probado en 3.13). No se necesita Docker ni servicios de pago.

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
| Empresa Demo A / B | `gerencia` | Gerencia | Tablero de capacidad |
| Empresa Demo A / B | `admin` | Administrador de la empresa | Tablero y auditoría de su empresa |
| Empresa Demo A / B | `despachador`, `conductor` | Despachador / Conductor | "Pantallas en construcción" (fases 3+) |
| (sin empresa) | `superadmin` | Superadministrador | Administración de empresas y auditoría global |

Sugerencia de recorrido: entrar como `gerencia` de la Empresa A, ver el tablero y exportar el CSV;
cerrar sesión y entrar a la Empresa B para comprobar que sus datos son distintos; entrar como
`superadmin`, crear una empresa, suspender la B y verificar que sus usuarios ya no pueden entrar.

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
`APP/Backend` (API, dominio, casos de uso, adaptadores, pruebas) · `APP/Frontend` (React + Vite) ·
`infra/` (Compose con PostgreSQL comentado) · `scripts/` · `docs/`.

## Notas
- `APP/Frontend/node_modules` es una unión hacia `%LOCALAPPDATA%\fleetplanner-tools` para que OneDrive
  no sincronice miles de archivos (D-015).
- Mensajes de la interfaz y de la API en español; identificadores de código en inglés.
