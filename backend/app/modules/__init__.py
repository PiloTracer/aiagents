"""Feature modules live here. Each module may define:

- models.py   (SQLAlchemy models using app.core.database.Base)
- schemas.py  (Pydantic models)
- service.py  (business logic)
- repository.py (data access)
- router.py   (FastAPI APIRouter exported as `router`)

Routers are auto-discovered and included; models are auto-imported
for Alembic autogeneration.
"""

