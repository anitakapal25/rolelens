"""Single-service entry point (free-tier deploys): the API under /api and the built frontend at /.

    uvicorn app.serve:app       # expects the Vite build in STATIC_DIR (default /app/static)

Local development and docker-compose keep using app.main:app with nginx in front.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.main import create_app


def create_serving_app(static_dir: Path) -> FastAPI:
    root = FastAPI(title="RoleLens", docs_url=None, redoc_url=None, openapi_url=None)
    root.mount("/api", create_app())
    root.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return root


app = create_serving_app(Path(os.environ.get("STATIC_DIR", "/app/static")))
