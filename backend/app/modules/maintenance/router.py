from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.module_loader import import_module_models, iter_submodules
from app.modules.users.bootstrap import ensure_default_admin
from app.modules.catalog.bootstrap import ensure_default_catalog
from app.modules.users.models import User


router = APIRouter(prefix="/maintenance", tags=["maintenance"])


DbDep = Annotated[Session, Depends(get_db)]


def require_superuser(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    return current_user


@router.get("/sync-tables")
def sync_tables(
    db: DbDep,
    _: Annotated[User, Depends(require_superuser)],
):
    """
    Ensure all discovered models have their tables created and run bootstraps.
    """
    engine = db.get_bind()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database engine unavailable")

    # Load all module models so Base.metadata is complete
    for module in iter_submodules("app.modules"):
        import_module_models(module)

    inspector = inspect(engine)
    known_tables_before = set(inspector.get_table_names())

    Base.metadata.create_all(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    known_tables_after = set(inspector.get_table_names())
    created_tables = sorted(known_tables_after - known_tables_before)

    ensure_default_admin(db)
    ensure_default_catalog(db)

    return {
        "status": "ok",
        "created_tables": created_tables,
        "total_known_tables": sorted(known_tables_after),
    }

