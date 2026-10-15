# Imagen unica de la demo (DEMO-ONLY): la API sirve tambien la interfaz compilada, en UN proceso.
# Repositorios en memoria: no escale a mas de una instancia ni de un worker.
#
# ESTADO: este Dockerfile NO se ha construido ni ejecutado (Docker no esta instalado en el PC de
# desarrollo). Sus pasos replican los comandos que si se ejecutaron localmente.
#
# Variables obligatorias en el hospedaje (nunca en el repositorio):
#   JWT_SIGNING_KEY            >= 32 caracteres aleatorios
#   DEMO_PASSWORD              >= 12 caracteres (usuarios gerencia, despachador, conductor, admin)
#   DEMO_SUPERADMIN_PASSWORD   >= 12 caracteres, distinta de la anterior
# El hospedaje define PORT; HOST y FRONTEND_DIST ya estan fijados abajo.

FROM node:22-slim AS web
WORKDIR /web
COPY APP/Frontend/package.json APP/Frontend/package-lock.json ./
RUN npm ci
COPY APP/Frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLEETPLANNER_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    FRONTEND_DIST=/app/dist
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY APP/Backend/requirements-runtime.lock ./
RUN pip install -r requirements-runtime.lock
COPY APP/Backend/pyproject.toml ./
COPY APP/Backend/src ./src
RUN pip install --no-deps .
COPY --from=web /web/dist /app/dist
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % os.environ.get('PORT','8000'),timeout=4)"
CMD ["python", "-m", "fleetplanner.bootstrap", "serve"]
