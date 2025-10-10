from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.autogenerate import api as autogen_api
from alembic.migration import MigrationContext

from .config import settings
from .database import Base
from sqlalchemy import create_engine


def _alembic_config() -> Config:
    # Resolve to project root where alembic.ini lives (container: /app/alembic.ini)
    here = Path(__file__).resolve()
    project_root = here.parents[2]
    ini_path = project_root / "alembic.ini"
    cfg = Config(str(ini_path))
    # Ensure database URL is passed; alembic.ini uses a placeholder
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    # Make paths relative to the project root
    cfg.set_main_option("script_location", str(project_root / "app" / "migrations"))
    return cfg


def _versions_dir() -> Path:
    here = Path(__file__).resolve()
    project_root = here.parents[2]
    return project_root / "app" / "migrations" / "versions"


def init_and_upgrade() -> None:
    cfg = _alembic_config()
    versions = _versions_dir()
    versions.mkdir(parents=True, exist_ok=True)

    # If there are no migration files yet, create an initial one automatically.
    has_any = any(versions.iterdir())
    if not has_any:
        command.revision(cfg, message="init", autogenerate=True)

    # Optionally auto-generate a new revision if model diffs are detected.
    do_autogen = (settings.is_dev and settings.AUTOGEN_MIGRATIONS_DEV) or (
        (not settings.is_dev) and settings.AUTOGEN_MIGRATIONS_PROD
    )

    if do_autogen:
        try:
            engine = create_engine(settings.DATABASE_URL)
            with engine.connect() as connection:
                mc = MigrationContext.configure(
                    connection, opts={
                        "compare_type": True,
                        "compare_server_default": True,
                        "target_metadata": Base.metadata,
                    }
                )
                diffs = autogen_api.produce_migrations(mc, Base.metadata)
                if not diffs.upgrade_ops.is_empty():
                    message = "autogen startup (dev)" if settings.is_dev else "autogen startup (prod)"
                    command.revision(cfg, message=message, autogenerate=True)
        except Exception:
            # Non-fatal: if autogen inspection fails, continue with upgrade
            pass

    # Always attempt to upgrade to head on startup
    command.upgrade(cfg, "head")
