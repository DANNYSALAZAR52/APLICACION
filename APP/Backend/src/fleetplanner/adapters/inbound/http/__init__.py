"""Adaptador HTTP (FastAPI): traduce solicitudes a casos de uso y errores a respuestas."""

from fleetplanner.adapters.inbound.http.app import HttpSettings, create_app

__all__ = ["HttpSettings", "create_app"]
