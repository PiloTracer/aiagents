from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.module_loader import collect_routers
from app.core.database import SessionLocal, ensure_core_schema
from app.core.qdrant_client import ensure_qdrant_ready
from app.modules.users.bootstrap import ensure_default_admin
from app.modules.catalog.bootstrap import ensure_default_catalog


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

    routers = collect_routers()
    # Ensure DB schema is present before routes are registered
    ensure_core_schema()

    for router in routers:
        app.include_router(router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.on_event("startup")
    def _startup():
        # Ensure the high-capacity vector store is reachable
        ensure_qdrant_ready()
        # Ensure default admin is present if configured
        db = SessionLocal()
        try:
            ensure_default_admin(db)
            ensure_default_catalog(db)
        finally:
            db.close()

    return app


app = create_app()

