# Cómo mostrar la demo a otras personas (PC o celular fuera de su red)

Última actualización: 2026-10-14. **DATOS DE DEMOSTRACIÓN**: la demo es sintética y de un solo proceso con
datos en memoria. Está pensada para una presentación guiada, no como servicio permanente.

## 1. Qué hace falta (y qué ya está hecho)

| Pieza | Estado |
|---|---|
| La API sirve también la interfaz compilada en un solo proceso y un solo puerto (sin Vite, sin CORS) | Implementada y **probada** (pruebas + arranque real local) |
| Contraseñas fijas de los usuarios por variable de entorno (`DEMO_PASSWORD`, `DEMO_SUPERADMIN_PASSWORD`) | Implementada y **probada** |
| `PORT`/`HOST` del hospedaje, proxy inverso, cookie `Secure`, HSTS, documentación apagada | Implementada; **probada solo en local** (no con un proxy real) |
| `Dockerfile` (Node compila la interfaz → Python ejecuta todo) | Escrito, **NO construido ni ejecutado** (Docker no está instalado en el PC de desarrollo) |
| Script para compartir desde su propio PC (`scripts/share-demo.ps1`) | Escrito; probado el arranque en local, **no con un túnel real** |

## 2. Usuarios

Mismas credenciales para las dos empresas de ejemplo (la empresa se elige en la pantalla de acceso):

| Empresa | Usuario | Rol | Qué verá |
|---|---|---|---|
| Empresa Demo A o B | `gerencia` | Gerencia | Capacidad, indicadores, patrones (puede reentrenar) |
| Empresa Demo A o B | `despachador` | Despachador | Torre de control, línea de tiempo, eventos y re-ruteo, indicadores, patrones |
| Empresa Demo A o B | `conductor` | Conductor | Su hoja de ruta (pensada para celular) |
| Empresa Demo A o B | `admin` | Administrador | Capacidad, maestros y parámetros, auditoría |
| (sin empresa) | `superadmin` | Superadministrador | Empresas y auditoría global |

- Todos menos `superadmin` comparten `DEMO_PASSWORD`; `superadmin` usa `DEMO_SUPERADMIN_PASSWORD`.
- Las contraseñas **no están en el repositorio**: usted las define como variables de entorno (mínimo 12
  caracteres, distintas entre sí). Si no las define, se generan aleatorias en cada arranque y se imprimen
  en el registro del servidor.
- Quien tenga la dirección y la contraseña puede operar la demo, **incluido reiniciar el día y reentrenar**.
  El estado es compartido: dos personas a la vez verán y alterarán el mismo día operativo.

## 3. Opción A — Railway (servidor temporal)

1. Suba el repositorio a GitHub (privado) sin `.env` (ya está ignorado).
2. En Railway: *New Project → Deploy from GitHub repo*. Detecta el `Dockerfile` de la raíz.
3. En *Variables* defina (valores suyos; no los escriba en el repositorio):
   - `JWT_SIGNING_KEY` — 48+ caracteres aleatorios.
   - `DEMO_PASSWORD` — mínimo 12 caracteres.
   - `DEMO_SUPERADMIN_PASSWORD` — mínimo 12, distinta de la anterior.
   - No defina `PORT`: Railway lo inyecta. `FLEETPLANNER_ENV=production`, `HOST` y `FRONTEND_DIST` ya vienen
     en la imagen.
4. *Settings → Networking → Generate Domain* para obtener la dirección `https://…up.railway.app`.
5. **Una sola réplica y un solo worker** (no escale): el estado vive en memoria.

Si falta una variable obligatoria, el contenedor termina con un mensaje claro en los registros
(`Falta JWT_SIGNING_KEY…`). Verifique en los registros que aparezca la tabla de usuarios con
"(la definida en el entorno)" y **no** contraseñas.

> No pude construir la imagen aquí. Si el *build* falla, copie el mensaje del registro: los pasos del
> `Dockerfile` son los mismos que se ejecutaron en local, así que lo esperable es un detalle de versión o de
> red, no de diseño.

## 4. Opción B — Desde su propio PC con un túnel (sin subir nada)

Útil si prefiere no usar un servidor. El PC debe quedar encendido y con la sesión abierta.

1. `powershell -ExecutionPolicy Bypass -File scripts\share-demo.ps1` — compila la interfaz, pide las dos
   contraseñas (no se muestran) y arranca todo en `http://127.0.0.1:8000`.
2. En otra ventana, abra un túnel HTTPS hacia ese puerto con la herramienta que prefiera; por ejemplo
   `cloudflared tunnel --url http://127.0.0.1:8000` (hay que instalarla aparte; no se instaló aquí).
3. Comparta la dirección `https://…` que imprime.

El túnel expone su PC solo a través de ese puerto y mientras esté abierto. Ciérrelo al terminar.

## 5. Antes de enseñarla

- Haga una prueba **desde su celular con datos móviles** (no desde la red del PC). Nunca se revisó la
  interfaz en un navegador real ni en un celular real durante el desarrollo: la hoja del conductor es
  *mobile-first* por diseño, no por inspección.
- Entre a *Torre de control* y a *Patrones detectados* una vez antes de la reunión: el primer plan del día
  toma ~3 s y el primer entrenamiento de ML ~3 s por empresa.
- El mapa carga teselas de OpenStreetMap: requiere internet en el dispositivo que lo mira.
- Si algo queda en un estado raro, *Reiniciar día* en la torre de control, o reinicie el servicio (se pierde
  todo lo creado: empresas nuevas, cambios de maestros, auditoría).

## 6. Riesgos y límites (leer antes de publicar la dirección)

- **Es una demo, no un sistema para datos reales.** No cargue información de personas ni empresas reales.
- La contraseña compartida es adecuada para una presentación; **cámbiela después** y no la reutilice.
- Hay límites de tasa en inicio de sesión y operaciones, pero no hay protección contra abuso masivo
  (WAF, CAPTCHA, MFA). No publique la dirección en abierto.
- Sin PostgreSQL ni Redis: al reiniciar se pierde el estado y las sesiones caducan.
- El flujo en tiempo real (SSE) pasa por el proxy del hospedaje o del túnel; **no se verificó** con ninguno.
  Si el proxy lo corta, la pantalla vuelve sola a consultar cada 2,5 s.
- Un solo proceso: unas pocas personas a la vez; no es una prueba de carga.
- `pip-audit` no se pudo ejecutar en este PC, así que no hay un análisis de vulnerabilidades de las
  dependencias de Python en esta entrega (sí `npm audit`: 0).
