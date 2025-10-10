from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.module_loader import collect_routers
from app.core.migrations import init_and_upgrade


def create_app() -> FastAPI:
    app = FastAPI(title="DLV2 API", version="0.1.0")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include module routers
    for router in collect_routers():
        app.include_router(router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.on_event("startup")
    def _startup():
        # Generate initial migration if missing and apply all migrations
        init_and_upgrade()

    return app


app = create_app()

