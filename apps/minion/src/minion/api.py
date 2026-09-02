"""HTTP surface.

Not a queue and not a UI — just a health check and whatever webhook routes the push
sources register on it.
"""

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Minion Agent", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app
