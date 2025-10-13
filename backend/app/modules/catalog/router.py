from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.modules.users.models import User
from .schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    AreaCreate,
    AreaRead,
    AreaUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserRoleAssignmentRequest,
)
from .service import CatalogService


router = APIRouter(prefix="/catalog", tags=["catalog"])


def require_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient privileges",
        )
    return current_user


DbDep = Annotated[Session, Depends(get_db)]
SuperuserDep = Annotated[User, Depends(require_superuser)]


@router.get("/areas", response_model=list[AreaRead])
def list_areas(db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    return svc.list_areas()


@router.post("/areas", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
def create_area(payload: AreaCreate, db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    try:
        return svc.create_area(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/areas/{area_id}", response_model=AreaRead)
def update_area(area_id: str, payload: AreaUpdate, db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    try:
        return svc.update_area(area_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/agents", response_model=list[AgentRead])
def list_agents(db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    return svc.list_agents()


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    try:
        return svc.create_agent(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/agents/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: str, payload: AgentUpdate, db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    try:
        return svc.update_agent(agent_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/roles", response_model=list[RoleRead])
def list_roles(db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    return svc.list_roles()


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    try:
        return svc.create_role(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/roles/{role_id}", response_model=RoleRead)
def update_role(role_id: str, payload: RoleUpdate, db: DbDep, _: SuperuserDep):
    svc = CatalogService(db)
    try:
        return svc.update_role(role_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/users/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
def assign_roles_to_user(
    user_id: str,
    payload: UserRoleAssignmentRequest,
    db: DbDep,
    _: SuperuserDep,
):
    svc = CatalogService(db)
    try:
        svc.assign_roles_to_user(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

