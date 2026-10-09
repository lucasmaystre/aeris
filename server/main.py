# Entrypoint for Vercel and `fastapi dev`.
from aeris_server.app import app

__all__ = ["app"]
