# Comandos reproducibles de la demo. Requiere `make`; en Windows sin make, ejecuta el comando
# de la derecha directamente en PowerShell desde APP/Backend (ver README.md).
# NOTA: este Makefile NO se ha ejecutado (make no está instalado en el entorno de desarrollo);
# los comandos equivalentes sí se ejecutaron a mano (ver docs/REGISTRO_DEMO.md).

PY := APP/Backend/.venv/Scripts/python
BACKEND := APP/Backend

.PHONY: install test lint security demo

install:
	python -m venv $(BACKEND)/.venv
	$(PY) -m pip install -r $(BACKEND)/requirements.lock
	$(PY) -m pip install -e $(BACKEND) --no-deps

test:
	cd $(BACKEND) && .venv/Scripts/python -m pytest --cov

lint:
	cd $(BACKEND) && .venv/Scripts/python -m ruff check src tests
	cd $(BACKEND) && .venv/Scripts/python -m mypy
	cd $(BACKEND) && .venv/Scripts/python -c "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())"

security:
	cd $(BACKEND) && .venv/Scripts/python -m bandit -r src
	cd $(BACKEND) && .venv/Scripts/python -m pip_audit

demo:
	cd $(BACKEND) && .venv/Scripts/python -m fleetplanner.bootstrap capacity

# Pendientes (no existen aún): up, seed (requieren PostgreSQL/Docker y las fases 2+).
